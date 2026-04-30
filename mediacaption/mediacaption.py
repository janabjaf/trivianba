"""MediaCaption cog for Red-DiscordBot.

Caption and edit images, GIFs, and videos directly inside Discord.
Author: jaffar21
"""
from __future__ import annotations

import asyncio
import functools
import io
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import aiohttp
import discord
from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageSequence,
)
from redbot.core import commands
from redbot.core.bot import Red

URL_REGEX = re.compile(r"https?://\S+")
TENOR_REGEX = re.compile(r"https?://(?:media\.)?tenor\.com/\S+")

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB input ceiling
MAX_OUTPUT_BYTES = 25 * 1024 * 1024
MAX_PIXELS_PER_SIDE = 4096
SEARCH_HISTORY_LIMIT = 25
DEFAULT_TIMEOUT = 60  # seconds for ffmpeg jobs

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
GIF_EXTS = (".gif",)
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".m4v")

FONTS_DIR = Path(__file__).parent / "fonts"
CAPTION_FONT_PATH = FONTS_DIR / "Anton-Regular.ttf"


class MediaError(commands.UserFeedbackCheckFailure):
    """Raised to send a clean error message back to the user."""


class MediaCaption(commands.Cog):
    """Caption, edit, and remix images, GIFs, and videos.

    All commands look for media in this order:
      1. The message you're replying to
      2. Attachments / URLs / embeds in your own message
      3. The most recent media posted in the channel
    """

    __version__ = "1.0.0"
    __author__ = "jaffar21"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Red-DiscordBot MediaCaption cog"}
        )
        self._ffmpeg = self._resolve_ffmpeg()

    @staticmethod
    def _resolve_ffmpeg() -> Optional[str]:
        """Prefer a system ffmpeg, fall back to the one bundled with imageio-ffmpeg."""
        sys_ffmpeg = shutil.which("ffmpeg")
        if sys_ffmpeg:
            return sys_ffmpeg
        try:
            import imageio_ffmpeg  # type: ignore

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    async def cog_unload(self) -> None:
        await self.session.close()

    # Red 3.5 end-user-data hooks (no data stored)
    async def red_get_data_for_user(self, *, user_id: int):
        return {}

    async def red_delete_data_for_user(self, **kwargs) -> None:
        return

    def format_help_for_context(self, ctx: commands.Context) -> str:  # type: ignore[override]
        pre = super().format_help_for_context(ctx)
        return (
            f"{pre}\n\n"
            f"Cog version: {self.__version__}\n"
            f"Author: {self.__author__}"
        )

    # ------------------------------------------------------------------
    # Media discovery
    # ------------------------------------------------------------------
    async def _find_media(
        self, ctx: commands.Context
    ) -> Tuple[bytes, str, str]:
        """Return ``(data, content_type, filename)`` or raise ``MediaError``."""
        # 1. Replied-to message
        ref_msg: Optional[discord.Message] = None
        if ctx.message.reference is not None:
            resolved = ctx.message.reference.resolved
            if isinstance(resolved, discord.Message):
                ref_msg = resolved
            elif ctx.message.reference.message_id:
                try:
                    ref_msg = await ctx.channel.fetch_message(
                        ctx.message.reference.message_id
                    )
                except (discord.NotFound, discord.Forbidden):
                    ref_msg = None

        for msg in (m for m in (ref_msg, ctx.message) if m is not None):
            found = await self._extract_from_message(msg)
            if found:
                return found

        # 2. Walk recent channel history
        try:
            async for msg in ctx.channel.history(limit=SEARCH_HISTORY_LIMIT):
                if msg.id == ctx.message.id:
                    continue
                found = await self._extract_from_message(msg)
                if found:
                    return found
        except discord.Forbidden:
            pass

        raise MediaError(
            "I couldn't find any image, GIF, or video. Attach one, reply to "
            "a message that has one, or post a link."
        )

    async def _extract_from_message(
        self, msg: discord.Message
    ) -> Optional[Tuple[bytes, str, str]]:
        # Attachments first - cheapest and highest quality
        for att in msg.attachments:
            ct = (att.content_type or "").lower()
            name = (att.filename or "file").lower()
            if ct.startswith(("image/", "video/")) or name.endswith(
                IMAGE_EXTS + GIF_EXTS + VIDEO_EXTS
            ):
                if att.size and att.size > MAX_DOWNLOAD_BYTES:
                    continue
                try:
                    data = await att.read()
                except (discord.HTTPException, discord.NotFound):
                    continue
                return data, ct or self._guess_content_type(name), name

        # Stickers (only static / lottie image-able ones via .url work as PNG)
        for st in msg.stickers:
            try:
                downloaded = await self._download(str(st.url))
            except Exception:
                downloaded = None
            if downloaded:
                data, ct = downloaded
                return data, ct, f"{st.name}.png"

        # Embed image / thumbnail / video / url
        for emb in msg.embeds:
            for source in (
                getattr(emb, "video", None),
                emb.image,
                emb.thumbnail,
            ):
                url = getattr(source, "url", None) if source else None
                if url:
                    downloaded = await self._download(url)
                    if downloaded:
                        data, ct = downloaded
                        return data, ct, self._name_from_url(url)
            if emb.url:
                downloaded = await self._download(emb.url)
                if downloaded:
                    data, ct = downloaded
                    return data, ct, self._name_from_url(emb.url)

        # URLs in the message body
        for match in URL_REGEX.finditer(msg.content or ""):
            url = match.group(0).rstrip(">.,)")
            downloaded = await self._download(url)
            if downloaded:
                data, ct = downloaded
                return data, ct, self._name_from_url(url)

        return None

    async def _download(self, url: str) -> Optional[Tuple[bytes, str]]:
        try:
            async with self.session.get(
                url, timeout=aiohttp.ClientTimeout(total=30), allow_redirects=True
            ) as resp:
                if resp.status != 200:
                    return None
                ct = (resp.content_type or "").lower()
                if not ct.startswith(("image/", "video/")):
                    return None
                clen = resp.content_length or 0
                if clen and clen > MAX_DOWNLOAD_BYTES:
                    return None
                buf = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    buf.extend(chunk)
                    if len(buf) > MAX_DOWNLOAD_BYTES:
                        return None
                return bytes(buf), ct
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    @staticmethod
    def _guess_content_type(name: str) -> str:
        name = name.lower()
        if name.endswith(".gif"):
            return "image/gif"
        for ext in IMAGE_EXTS:
            if name.endswith(ext):
                return "image/" + ext.lstrip(".")
        for ext in VIDEO_EXTS:
            if name.endswith(ext):
                return "video/" + ext.lstrip(".")
        return "application/octet-stream"

    @staticmethod
    def _name_from_url(url: str) -> str:
        tail = url.split("?")[0].rstrip("/").split("/")[-1]
        return tail or "media"

    # ------------------------------------------------------------------
    # Media classification
    # ------------------------------------------------------------------
    @staticmethod
    def _is_gif(content_type: str, data: bytes) -> bool:
        if content_type == "image/gif":
            return True
        return data[:6] in (b"GIF87a", b"GIF89a")

    @staticmethod
    def _is_video(content_type: str, data: bytes) -> bool:
        if content_type.startswith("video/"):
            return True
        # ftyp atom for mp4/mov
        return b"ftyp" in data[4:32]

    # ------------------------------------------------------------------
    # Text fitting + caption rendering (PIL)
    # ------------------------------------------------------------------
    @staticmethod
    def _wrap_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> List[str]:
        # Respect explicit newlines from the user.
        out: List[str] = []
        for paragraph in text.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                out.append("")
                continue
            line = words[0]
            for word in words[1:]:
                test = f"{line} {word}"
                if draw.textlength(test, font=font) <= max_width:
                    line = test
                else:
                    out.append(line)
                    line = word
            out.append(line)
        return out

    @classmethod
    def _fit_font(
        cls,
        draw: ImageDraw.ImageDraw,
        text: str,
        max_width: int,
        max_height: int,
        font_path: str,
        max_size: int,
        min_size: int = 18,
    ) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
        size = max_size
        last_font: Optional[ImageFont.FreeTypeFont] = None
        last_lines: List[str] = []
        while size >= min_size:
            font = ImageFont.truetype(font_path, size)
            lines = cls._wrap_text(draw, text, font, max_width)
            ascent, descent = font.getmetrics()
            line_height = ascent + descent
            line_spacing = int(line_height * 0.15)
            block_h = line_height * len(lines) + line_spacing * max(
                len(lines) - 1, 0
            )
            widest = max(
                (draw.textlength(l, font=font) for l in lines), default=0
            )
            if block_h <= max_height and widest <= max_width:
                return font, lines
            last_font, last_lines = font, lines
            size = max(int(size * 0.9), size - 2)
            if size == max_size:
                size -= 2
        return (
            last_font or ImageFont.truetype(font_path, min_size),
            last_lines or cls._wrap_text(
                draw,
                text,
                ImageFont.truetype(font_path, min_size),
                max_width,
            ),
        )

    @classmethod
    def _render_caption_strip(
        cls, width: int, max_height: int, text: str, font_path: str
    ) -> Image.Image:
        """Render the white caption bar with black text used by ``caption``/``bottom``."""
        side_padding = max(int(width * 0.04), 18)
        max_text_width = width - 2 * side_padding
        target_size = max(int(width / 11), 30)
        # Measure on a throwaway canvas
        tmp = Image.new("RGB", (width, 100), "white")
        tdraw = ImageDraw.Draw(tmp)
        font, lines = cls._fit_font(
            tdraw,
            text,
            max_text_width,
            max_height,
            font_path,
            max_size=target_size,
            min_size=20,
        )
        ascent, descent = font.getmetrics()
        line_height = ascent + descent
        line_spacing = int(line_height * 0.15)
        block_h = line_height * len(lines) + line_spacing * max(
            len(lines) - 1, 0
        )
        bar_pad = max(int(line_height * 0.45), 18)
        bar_h = block_h + 2 * bar_pad
        strip = Image.new("RGBA", (width, bar_h), (255, 255, 255, 255))
        sdraw = ImageDraw.Draw(strip)
        y = bar_pad - descent // 2
        for line in lines:
            line_w = sdraw.textlength(line, font=font)
            x = (width - line_w) / 2
            sdraw.text((x, y), line, fill=(0, 0, 0, 255), font=font)
            y += line_height + line_spacing
        return strip

    @classmethod
    def _add_caption_to_frame(
        cls, img: Image.Image, text: str, position: str
    ) -> Image.Image:
        img = img.convert("RGBA")
        w, h = img.size
        max_caption_h = max(int(h * 0.55), 200)
        strip = cls._render_caption_strip(
            w, max_caption_h, text, str(CAPTION_FONT_PATH)
        )
        bar_h = strip.size[1]
        new_h = h + bar_h
        canvas = Image.new("RGBA", (w, new_h), (255, 255, 255, 255))
        if position == "top":
            canvas.paste(strip, (0, 0), strip)
            canvas.paste(img, (0, bar_h), img)
        else:
            canvas.paste(img, (0, 0), img)
            canvas.paste(strip, (0, h), strip)
        return canvas

    @classmethod
    def _add_meme_text_to_frame(
        cls, img: Image.Image, top: str, bottom: str
    ) -> Image.Image:
        img = img.convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        side_padding = max(int(w * 0.04), 12)
        max_text_width = w - 2 * side_padding
        max_block_h = int(h * 0.32)

        def draw_block(text: str, where: str) -> None:
            if not text:
                return
            text = text.upper()
            target = max(int(h / 8), 32)
            font, lines = cls._fit_font(
                draw,
                text,
                max_text_width,
                max_block_h,
                str(CAPTION_FONT_PATH),
                max_size=target,
                min_size=24,
            )
            stroke = max(int(font.size / 16), 2)
            ascent, descent = font.getmetrics()
            line_height = ascent + descent
            line_spacing = int(line_height * 0.1)
            block_h = line_height * len(lines) + line_spacing * max(
                len(lines) - 1, 0
            )
            if where == "top":
                y = max(int(h * 0.025), 10)
            else:
                y = h - block_h - max(int(h * 0.025), 10)
            for line in lines:
                line_w = draw.textlength(line, font=font)
                x = (w - line_w) / 2
                draw.text(
                    (x, y),
                    line,
                    fill="white",
                    font=font,
                    stroke_width=stroke,
                    stroke_fill="black",
                )
                y += line_height + line_spacing

        draw_block(top, "top")
        draw_block(bottom, "bottom")
        return img

    @classmethod
    def _add_speech_bubble_to_frame(cls, img: Image.Image) -> Image.Image:
        """Cut a transparent speech-bubble notch out of the top of the frame."""
        img = img.convert("RGBA")
        w, h = img.size
        bubble_h = max(int(h * 0.22), 80)
        # Build alpha mask: white where image is visible, transparent where bubble is
        mask = Image.new("L", (w, bubble_h), 255)
        d = ImageDraw.Draw(mask)
        # Main rounded rectangle
        rect_w = int(w * 0.94)
        rect_h = int(bubble_h * 0.78)
        rect_x = (w - rect_w) // 2
        rect_y = int(bubble_h * 0.05)
        d.rounded_rectangle(
            (rect_x, rect_y, rect_x + rect_w, rect_y + rect_h),
            radius=int(min(rect_w, rect_h) * 0.18),
            fill=0,
        )
        # Tail - small triangle off the bottom-left of the bubble
        tail_w = int(w * 0.09)
        tail_h = int(bubble_h * 0.32)
        tail_x = int(w * 0.18)
        tail_y = rect_y + rect_h - 2
        d.polygon(
            [
                (tail_x, tail_y),
                (tail_x + tail_w, tail_y),
                (tail_x + int(tail_w * 0.25), tail_y + tail_h),
            ],
            fill=0,
        )
        # Apply mask only to the top region of the image
        top_region = img.crop((0, 0, w, bubble_h))
        top_alpha = top_region.split()[-1]
        new_alpha = ImageChops_multiply(top_alpha, mask)
        top_region.putalpha(new_alpha)
        result = img.copy()
        result.paste(top_region, (0, 0), top_region)
        return result

    # ------------------------------------------------------------------
    # Generic image / GIF processing
    # ------------------------------------------------------------------
    def _open_image(self, data: bytes) -> Image.Image:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
            return img
        except Exception as exc:  # pragma: no cover - PIL message varies
            raise MediaError(f"Couldn't read that image: {exc}") from exc

    @staticmethod
    def _shrink_if_huge(img: Image.Image) -> Image.Image:
        w, h = img.size
        long_side = max(w, h)
        if long_side <= MAX_PIXELS_PER_SIDE:
            return img
        scale = MAX_PIXELS_PER_SIDE / long_side
        return img.resize(
            (max(int(w * scale), 1), max(int(h * scale), 1)),
            Image.LANCZOS,
        )

    def _process_static(
        self,
        data: bytes,
        op,
        out_format: str = "PNG",
    ) -> Tuple[bytes, str]:
        img = self._shrink_if_huge(self._open_image(data))
        result = op(img)
        buf = io.BytesIO()
        save_kwargs: dict = {}
        if out_format.upper() == "JPEG":
            result = result.convert("RGB")
            save_kwargs["quality"] = 92
            save_kwargs["optimize"] = True
        result.save(buf, out_format, **save_kwargs)
        return buf.getvalue(), out_format.lower()

    def _process_gif(
        self, data: bytes, op
    ) -> Tuple[bytes, str]:
        src = self._open_image(data)
        frames: List[Image.Image] = []
        durations: List[int] = []
        loop = src.info.get("loop", 0)
        for frame in ImageSequence.Iterator(src):
            durations.append(frame.info.get("duration", 80))
            converted = self._shrink_if_huge(frame.convert("RGBA"))
            frames.append(op(converted).convert("RGBA"))
        if not frames:
            raise MediaError("That GIF had no frames I could read.")
        buf = io.BytesIO()
        frames[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=loop,
            disposal=2,
            optimize=False,
        )
        return buf.getvalue(), "gif"

    # ------------------------------------------------------------------
    # Video processing via ffmpeg
    # ------------------------------------------------------------------
    def _require_ffmpeg(self) -> None:
        if not self._ffmpeg:
            raise MediaError(
                "Couldn't find ffmpeg. The `imageio-ffmpeg` requirement should "
                "have provided one — try `[p]cog install jaffar-cogs mediacaption` "
                "again, then `[p]reload mediacaption`."
            )

    async def _run_ffmpeg(
        self, args: Sequence[str], timeout: int = DEFAULT_TIMEOUT
    ) -> None:
        self._require_ffmpeg()
        proc = await asyncio.create_subprocess_exec(
            self._ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise MediaError("Video processing took too long and was cancelled.")
        if proc.returncode != 0:
            err = (stderr or b"").decode(errors="replace").strip().splitlines()
            tail = "\n".join(err[-5:]) if err else "unknown ffmpeg error"
            raise MediaError(f"ffmpeg failed:\n```\n{tail}\n```")

    _DIMS_REGEX = re.compile(r",\s*(\d{2,5})x(\d{2,5})(?:\s|,|\[)")

    async def _video_dimensions(self, path: str) -> Tuple[int, int]:
        """Probe video dimensions by parsing ``ffmpeg -i`` stderr output.

        Avoids depending on ``ffprobe`` (which the bundled imageio-ffmpeg
        binary does not include).
        """
        if not self._ffmpeg:
            return (0, 0)
        proc = await asyncio.create_subprocess_exec(
            self._ffmpeg,
            "-hide_banner",
            "-i",
            path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        text = (stderr or b"").decode(errors="replace")
        for line in text.splitlines():
            if "Video:" not in line:
                continue
            match = self._DIMS_REGEX.search(line)
            if match:
                return int(match.group(1)), int(match.group(2))
        return (0, 0)

    async def _caption_video(
        self, data: bytes, text: str, position: str
    ) -> Tuple[bytes, str]:
        self._require_ffmpeg()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.mp4")
            out_path = os.path.join(tmp, "out.mp4")
            cap_path = os.path.join(tmp, "cap.png")
            with open(in_path, "wb") as f:
                f.write(data)
            w, h = await self._video_dimensions(in_path)
            if not w or not h:
                raise MediaError("Couldn't read that video's dimensions.")
            # ffmpeg requires even pixel dims for libx264
            target_w = w if w % 2 == 0 else w - 1
            strip = await asyncio.get_running_loop().run_in_executor(
                None,
                functools.partial(
                    self._render_caption_strip,
                    target_w,
                    max(int(h * 0.55), 200),
                    text,
                    str(CAPTION_FONT_PATH),
                ),
            )
            bar_h = strip.size[1]
            if bar_h % 2 == 1:
                bar_h += 1
                new_strip = Image.new(
                    "RGBA", (target_w, bar_h), (255, 255, 255, 255)
                )
                new_strip.paste(strip, (0, 0), strip)
                strip = new_strip
            strip.convert("RGB").save(cap_path, "PNG")
            if position == "top":
                fc = (
                    f"[0:v]scale={target_w}:-2,pad={target_w}:ih+{bar_h}:0:{bar_h}:white[v];"
                    f"[v][1:v]overlay=0:0[outv]"
                )
            else:
                fc = (
                    f"[0:v]scale={target_w}:-2,pad={target_w}:ih+{bar_h}:0:0:white[v];"
                    f"[v][1:v]overlay=0:main_h-{bar_h}[outv]"
                )
            await self._run_ffmpeg(
                [
                    "-i",
                    in_path,
                    "-i",
                    cap_path,
                    "-filter_complex",
                    fc,
                    "-map",
                    "[outv]",
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-c:a",
                    "copy",
                    "-movflags",
                    "+faststart",
                    out_path,
                ]
            )
            with open(out_path, "rb") as f:
                return f.read(), "mp4"

    async def _video_simple_filter(
        self,
        data: bytes,
        vf: str,
        af: Optional[str] = None,
        extra: Optional[Sequence[str]] = None,
    ) -> Tuple[bytes, str]:
        self._require_ffmpeg()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.mp4")
            out_path = os.path.join(tmp, "out.mp4")
            with open(in_path, "wb") as f:
                f.write(data)
            args: List[str] = ["-i", in_path]
            if extra:
                args.extend(extra)
            if vf:
                args.extend(["-vf", vf])
            if af:
                args.extend(["-af", af])
            args.extend(
                [
                    "-map",
                    "0:v",
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac" if af else "copy",
                    "-movflags",
                    "+faststart",
                    out_path,
                ]
            )
            await self._run_ffmpeg(args)
            with open(out_path, "rb") as f:
                return f.read(), "mp4"

    async def _video_to_gif(self, data: bytes) -> Tuple[bytes, str]:
        self._require_ffmpeg()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.mp4")
            palette = os.path.join(tmp, "palette.png")
            out_path = os.path.join(tmp, "out.gif")
            with open(in_path, "wb") as f:
                f.write(data)
            await self._run_ffmpeg(
                [
                    "-i",
                    in_path,
                    "-vf",
                    "fps=15,scale=480:-1:flags=lanczos,palettegen",
                    palette,
                ]
            )
            await self._run_ffmpeg(
                [
                    "-i",
                    in_path,
                    "-i",
                    palette,
                    "-lavfi",
                    "fps=15,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse",
                    out_path,
                ]
            )
            with open(out_path, "rb") as f:
                return f.read(), "gif"

    async def _gif_to_mp4(self, data: bytes) -> Tuple[bytes, str]:
        self._require_ffmpeg()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.gif")
            out_path = os.path.join(tmp, "out.mp4")
            with open(in_path, "wb") as f:
                f.write(data)
            await self._run_ffmpeg(
                [
                    "-i",
                    in_path,
                    "-movflags",
                    "+faststart",
                    "-pix_fmt",
                    "yuv420p",
                    "-vf",
                    "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    out_path,
                ]
            )
            with open(out_path, "rb") as f:
                return f.read(), "mp4"

    # ------------------------------------------------------------------
    # Dispatch: pick image / gif / video pipeline for an op
    # ------------------------------------------------------------------
    async def _apply_visual_op(
        self,
        ctx: commands.Context,
        op_image,
        op_video_vf: Optional[str] = None,
        out_image_format: str = "PNG",
    ) -> None:
        """Apply ``op_image`` to images / GIFs and ``op_video_vf`` to videos."""
        data, ct, fname = await self._find_media(ctx)
        loop = asyncio.get_running_loop()
        async with ctx.typing():
            if self._is_video(ct, data):
                if op_video_vf is None:
                    raise MediaError(
                        "That operation isn't supported on videos."
                    )
                out, ext = await self._video_simple_filter(data, op_video_vf)
            elif self._is_gif(ct, data):
                out, ext = await loop.run_in_executor(
                    None, functools.partial(self._process_gif, data, op_image)
                )
            else:
                out, ext = await loop.run_in_executor(
                    None,
                    functools.partial(
                        self._process_static, data, op_image, out_image_format
                    ),
                )
        await self._send_result(ctx, out, ext)

    async def _send_result(
        self, ctx: commands.Context, data: bytes, ext: str
    ) -> None:
        if len(data) > MAX_OUTPUT_BYTES:
            raise MediaError(
                f"Result is too big to upload ({len(data) / 1024 / 1024:.1f} MB)."
            )
        # Respect the channel's actual upload limit when we can read it
        try:
            limit = ctx.guild.filesize_limit if ctx.guild else MAX_OUTPUT_BYTES
        except AttributeError:
            limit = MAX_OUTPUT_BYTES
        if len(data) > limit:
            raise MediaError(
                f"Result is {len(data) / 1024 / 1024:.1f} MB but this server "
                f"only allows uploads up to {limit / 1024 / 1024:.1f} MB."
            )
        file = discord.File(io.BytesIO(data), filename=f"output.{ext}")
        try:
            await ctx.reply(file=file, mention_author=False)
        except discord.HTTPException:
            await ctx.send(file=file)

    # ------------------------------------------------------------------
    # Error handler for the cog
    # ------------------------------------------------------------------
    async def cog_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.UserFeedbackCheckFailure):
            try:
                await ctx.send(str(error))
            except discord.HTTPException:
                pass
            return
        # Let Red handle anything else
        await ctx.bot.on_command_error(ctx, error, unhandled_by_cog=True)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    @commands.group(name="media", invoke_without_command=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def media(self, ctx: commands.Context) -> None:
        """Edit, caption, and remix images, GIFs, and videos."""
        await ctx.send_help()

    # ----- Captions -----
    @media.command(name="caption")
    async def media_caption(
        self, ctx: commands.Context, *, text: str
    ) -> None:
        """Add an iFunny-style white caption bar with black text on top.

        Examples:
          `[p]media caption Uno hana`
          `[p]media caption when bro forgets the prefix`
        """
        text = text.strip().strip('"').strip("'")
        if not text:
            raise MediaError("Give me some text for the caption.")
        await self._caption_dispatch(ctx, text, "top")

    @media.command(name="bottom")
    async def media_bottom(
        self, ctx: commands.Context, *, text: str
    ) -> None:
        """Same as `caption`, but the bar is glued to the bottom."""
        text = text.strip().strip('"').strip("'")
        if not text:
            raise MediaError("Give me some text for the caption.")
        await self._caption_dispatch(ctx, text, "bottom")

    async def _caption_dispatch(
        self, ctx: commands.Context, text: str, position: str
    ) -> None:
        data, ct, _ = await self._find_media(ctx)
        loop = asyncio.get_running_loop()
        async with ctx.typing():
            if self._is_video(ct, data):
                out, ext = await self._caption_video(data, text, position)
            elif self._is_gif(ct, data):
                op = functools.partial(
                    self._add_caption_to_frame, text=text, position=position
                )
                out, ext = await loop.run_in_executor(
                    None, functools.partial(self._process_gif, data, op)
                )
            else:
                op = functools.partial(
                    self._add_caption_to_frame, text=text, position=position
                )
                out, ext = await loop.run_in_executor(
                    None,
                    functools.partial(
                        self._process_static, data, op, "PNG"
                    ),
                )
        await self._send_result(ctx, out, ext)

    @media.command(name="meme")
    async def media_meme(
        self, ctx: commands.Context, *, text: str
    ) -> None:
        """Classic Impact-style meme text. Use `|` to split top and bottom.

        Examples:
          `[p]media meme top text | bottom text`
          `[p]media meme one does not simply` (top only)
          `[p]media meme | only on the bottom`
        """
        if "|" in text:
            top, bottom = (s.strip() for s in text.split("|", 1))
        else:
            top, bottom = text.strip(), ""
        if not top and not bottom:
            raise MediaError("Give me some text.")
        op = functools.partial(
            self._add_meme_text_to_frame, top=top, bottom=bottom
        )
        await self._apply_visual_op(ctx, op, out_image_format="PNG")

    @media.command(name="speechbubble", aliases=["bubble"])
    async def media_speechbubble(self, ctx: commands.Context) -> None:
        """Cut a transparent speech bubble out of the top of the image."""
        await self._apply_visual_op(
            ctx, self._add_speech_bubble_to_frame, out_image_format="PNG"
        )

    # ----- Filters -----
    @media.command(name="deepfry")
    async def media_deepfry(self, ctx: commands.Context) -> None:
        """Cook the image until it's crispy."""
        await self._apply_visual_op(
            ctx, self._deepfry, out_image_format="JPEG"
        )

    @media.command(name="jpeg", aliases=["needsmorejpeg"])
    async def media_jpeg(
        self, ctx: commands.Context, quality: int = 1
    ) -> None:
        """Crush the image with terrible JPEG quality (1-95, default 1)."""
        quality = max(1, min(quality, 95))
        op = functools.partial(self._jpeg_crush, quality=quality)
        await self._apply_visual_op(ctx, op, out_image_format="JPEG")

    @media.command(name="invert")
    async def media_invert(self, ctx: commands.Context) -> None:
        """Invert the colors."""
        await self._apply_visual_op(
            ctx,
            self._invert,
            op_video_vf="negate",
        )

    @media.command(name="grayscale", aliases=["bw", "greyscale"])
    async def media_grayscale(self, ctx: commands.Context) -> None:
        """Drain all the color."""
        await self._apply_visual_op(
            ctx,
            self._grayscale,
            op_video_vf="hue=s=0",
        )

    @media.command(name="blur")
    async def media_blur(
        self, ctx: commands.Context, radius: int = 6
    ) -> None:
        """Gaussian blur the image (radius 1-30, default 6)."""
        radius = max(1, min(radius, 30))
        op = functools.partial(self._blur, radius=radius)
        await self._apply_visual_op(
            ctx,
            op,
            op_video_vf=f"boxblur={radius}",
        )

    @media.command(name="pixelate", aliases=["pixel"])
    async def media_pixelate(
        self, ctx: commands.Context, size: int = 12
    ) -> None:
        """Make the image tiny then huge again. Block size 2-64."""
        size = max(2, min(size, 64))
        op = functools.partial(self._pixelate, block=size)
        await self._apply_visual_op(
            ctx,
            op,
            op_video_vf=f"scale=iw/{size}:ih/{size},scale=iw*{size}:ih*{size}:flags=neighbor",
        )

    @media.command(name="rotate")
    async def media_rotate(
        self, ctx: commands.Context, degrees: int = 90
    ) -> None:
        """Rotate by N degrees (clockwise)."""
        degrees = degrees % 360
        op = functools.partial(self._rotate, degrees=degrees)
        # ffmpeg's rotate filter wants radians and uses CCW, so we flip the sign
        rad = -degrees * 3.141592653589793 / 180
        await self._apply_visual_op(
            ctx,
            op,
            op_video_vf=f"rotate={rad}:fillcolor=black",
        )

    @media.command(name="flip")
    async def media_flip(self, ctx: commands.Context) -> None:
        """Flip horizontally (mirror)."""
        await self._apply_visual_op(
            ctx, self._flip_horizontal, op_video_vf="hflip"
        )

    @media.command(name="flop")
    async def media_flop(self, ctx: commands.Context) -> None:
        """Flip vertically (upside down)."""
        await self._apply_visual_op(
            ctx, self._flip_vertical, op_video_vf="vflip"
        )

    # ----- Time-based: video / gif only -----
    @media.command(name="reverse")
    async def media_reverse(self, ctx: commands.Context) -> None:
        """Play a video or GIF backwards."""
        data, ct, _ = await self._find_media(ctx)
        loop = asyncio.get_running_loop()
        async with ctx.typing():
            if self._is_video(ct, data):
                out, ext = await self._video_simple_filter(
                    data, vf="reverse", af="areverse"
                )
            elif self._is_gif(ct, data):
                def reverse_gif(data_: bytes) -> Tuple[bytes, str]:
                    src = self._open_image(data_)
                    frames: List[Image.Image] = []
                    durations: List[int] = []
                    for f in ImageSequence.Iterator(src):
                        durations.append(f.info.get("duration", 80))
                        frames.append(f.convert("RGBA").copy())
                    frames.reverse()
                    durations.reverse()
                    buf = io.BytesIO()
                    frames[0].save(
                        buf,
                        format="GIF",
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations,
                        loop=src.info.get("loop", 0),
                        disposal=2,
                    )
                    return buf.getvalue(), "gif"

                out, ext = await loop.run_in_executor(
                    None, functools.partial(reverse_gif, data)
                )
            else:
                raise MediaError("Reverse only works on videos or GIFs.")
        await self._send_result(ctx, out, ext)

    @media.command(name="speed")
    async def media_speed(
        self, ctx: commands.Context, multiplier: float = 2.0
    ) -> None:
        """Change video speed (0.25-4x)."""
        if not 0.25 <= multiplier <= 4.0:
            raise MediaError("Multiplier must be between 0.25 and 4.")
        data, ct, _ = await self._find_media(ctx)
        if not self._is_video(ct, data):
            raise MediaError("`speed` works on videos only - try `togif` first.")
        # setpts wants the inverse: faster = smaller pts
        pts = 1.0 / multiplier
        # atempo only accepts 0.5-2.0 per filter; chain if needed
        atempo = self._build_atempo(multiplier)
        async with ctx.typing():
            out, ext = await self._video_simple_filter(
                data, vf=f"setpts={pts}*PTS", af=atempo
            )
        await self._send_result(ctx, out, ext)

    @staticmethod
    def _build_atempo(multiplier: float) -> str:
        chain: List[str] = []
        remaining = multiplier
        while remaining > 2.0:
            chain.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            chain.append("atempo=0.5")
            remaining /= 0.5
        chain.append(f"atempo={remaining:.4f}")
        return ",".join(chain)

    @media.command(name="togif")
    async def media_togif(self, ctx: commands.Context) -> None:
        """Convert a video to a GIF."""
        data, ct, _ = await self._find_media(ctx)
        if not self._is_video(ct, data):
            raise MediaError("That isn't a video.")
        async with ctx.typing():
            out, ext = await self._video_to_gif(data)
        await self._send_result(ctx, out, ext)

    @media.command(name="tomp4", aliases=["togifv"])
    async def media_tomp4(self, ctx: commands.Context) -> None:
        """Convert a GIF to MP4 (much smaller, looks better)."""
        data, ct, _ = await self._find_media(ctx)
        if not self._is_gif(ct, data):
            raise MediaError("That isn't a GIF.")
        async with ctx.typing():
            out, ext = await self._gif_to_mp4(data)
        await self._send_result(ctx, out, ext)

    @media.command(name="info")
    async def media_info(self, ctx: commands.Context) -> None:
        """Show info about the media in / above this message."""
        data, ct, fname = await self._find_media(ctx)
        size_mb = len(data) / 1024 / 1024
        kind = (
            "video"
            if self._is_video(ct, data)
            else "GIF"
            if self._is_gif(ct, data)
            else "image"
        )
        embed = discord.Embed(
            title="Media info",
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Type", value=f"{kind} ({ct or 'unknown'})")
        embed.add_field(name="Size", value=f"{size_mb:.2f} MB")
        embed.add_field(name="Filename", value=fname or "-", inline=False)
        if not self._is_video(ct, data):
            try:
                img = self._open_image(data)
                embed.add_field(
                    name="Dimensions",
                    value=f"{img.size[0]} x {img.size[1]}",
                )
                if self._is_gif(ct, data):
                    n = sum(1 for _ in ImageSequence.Iterator(img))
                    embed.add_field(name="Frames", value=str(n))
            except MediaError:
                pass
        elif self._ffmpeg:
            with tempfile.NamedTemporaryFile(
                suffix=".mp4", delete=False
            ) as tmp:
                tmp.write(data)
                path = tmp.name
            try:
                w, h = await self._video_dimensions(path)
                if w and h:
                    embed.add_field(
                        name="Dimensions", value=f"{w} x {h}"
                    )
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Pure image filter primitives
    # ------------------------------------------------------------------
    @staticmethod
    def _invert(img: Image.Image) -> Image.Image:
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            rgb = Image.merge("RGB", (r, g, b))
            inv = ImageOps.invert(rgb)
            ir, ig, ib = inv.split()
            return Image.merge("RGBA", (ir, ig, ib, a))
        return ImageOps.invert(img.convert("RGB"))

    @staticmethod
    def _grayscale(img: Image.Image) -> Image.Image:
        if img.mode == "RGBA":
            gray = ImageOps.grayscale(img.convert("RGB")).convert("RGB")
            r, g, b = gray.split()
            return Image.merge("RGBA", (r, g, b, img.split()[-1]))
        return ImageOps.grayscale(img.convert("RGB")).convert("RGB")

    @staticmethod
    def _blur(img: Image.Image, radius: int) -> Image.Image:
        return img.filter(ImageFilter.GaussianBlur(radius=radius))

    @staticmethod
    def _pixelate(img: Image.Image, block: int) -> Image.Image:
        w, h = img.size
        small = img.resize(
            (max(w // block, 1), max(h // block, 1)), Image.NEAREST
        )
        return small.resize((w, h), Image.NEAREST)

    @staticmethod
    def _rotate(img: Image.Image, degrees: int) -> Image.Image:
        return img.rotate(-degrees, expand=True, resample=Image.BICUBIC)

    @staticmethod
    def _flip_horizontal(img: Image.Image) -> Image.Image:
        return ImageOps.mirror(img)

    @staticmethod
    def _flip_vertical(img: Image.Image) -> Image.Image:
        return ImageOps.flip(img)

    @staticmethod
    def _jpeg_crush(img: Image.Image, quality: int) -> Image.Image:
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        buf.seek(0)
        return Image.open(buf).convert("RGB")

    @staticmethod
    def _deepfry(img: Image.Image) -> Image.Image:
        img = img.convert("RGB")
        w, h = img.size
        small = img.resize(
            (max(w // 2, 1), max(h // 2, 1)), Image.LANCZOS
        )
        small = ImageEnhance.Color(small).enhance(4.0)
        small = ImageEnhance.Contrast(small).enhance(1.7)
        small = ImageEnhance.Sharpness(small).enhance(8.0)
        for q in (10, 6, 4):
            buf = io.BytesIO()
            small.save(buf, "JPEG", quality=q)
            buf.seek(0)
            small = Image.open(buf).convert("RGB")
        r, g, b = small.split()
        r = ImageEnhance.Brightness(r).enhance(1.25)
        small = Image.merge("RGB", (r, g, b))
        return small.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------
# Local helper to avoid importing PIL.ImageChops at module top
# ------------------------------------------------------------------
def ImageChops_multiply(a: Image.Image, b: Image.Image) -> Image.Image:
    from PIL import ImageChops

    return ImageChops.multiply(a, b)
