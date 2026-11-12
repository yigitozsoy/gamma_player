"""Desteklenen dosya türleri ve sınıflandırma."""
import os

VIDEO_EXT = {
    ".mp4", ".m4v", ".mkv", ".mk3d", ".webm", ".avi", ".mov", ".qt", ".wmv", ".asf", ".flv", ".f4v",
    ".ts", ".mts", ".m2ts", ".m2t", ".tp", ".trp", ".vob", ".ogv", ".ogm", ".3gp", ".3g2", ".divx",
    ".xvid", ".rm", ".rmvb", ".mpg", ".mpeg", ".mpe", ".mpv", ".m1v", ".m2v", ".mp2v", ".dv", ".mxf",
    ".nsv", ".nuv", ".amv", ".evo", ".y4m", ".h264", ".h265", ".hevc", ".264", ".265", ".gxf",
    ".bik", ".wtv", ".dvr-ms", ".ivf", ".av1", ".webm", ".swf", ".roq",
}

AUDIO_EXT = {
    ".mp3", ".m4a", ".m4b", ".aac", ".flac", ".wav", ".wave", ".ogg", ".oga", ".opus", ".wma",
    ".alac", ".aif", ".aiff", ".aifc", ".ape", ".wv", ".mka", ".ac3", ".eac3", ".dts", ".mp2",
    ".mpa", ".amr", ".awb", ".au", ".snd", ".mid", ".midi", ".kar", ".mod", ".xm", ".it", ".s3m",
    ".tta", ".tak", ".spx", ".caf", ".w64", ".dsf", ".dff", ".gsm", ".voc", ".weba", ".mpc", ".ra",
}

IMAGE_EXT = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".pjpeg", ".pjp", ".png", ".apng", ".gif", ".webp", ".bmp",
    ".dib", ".ico", ".cur", ".icns", ".tif", ".tiff", ".heic", ".heif", ".hif", ".avif", ".jxl",
    ".svg", ".svgz", ".tga", ".qoi", ".ppm", ".pgm", ".pbm", ".pnm", ".pcx", ".psd", ".dds",
    ".jp2", ".j2k", ".jpf", ".jpx", ".xbm", ".xpm", ".wbmp", ".sgi", ".rgb", ".eps", ".im",
    ".blp", ".ftex", ".msp", ".fits", ".exr", ".hdr",
}

# 3D modeller (model_io.py okur)
MODEL_EXT = {".stl", ".obj", ".ply", ".off", ".glb", ".gltf", ".3mf",
             ".step", ".stp", ".iges", ".igs"}   # CAD: isteğe bağlı STEP motoru (model_io.load_cad)

SUBTITLE_EXT = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".smi", ".sami", ".txt", ".usf", ".ttml", ".dfxp", ".mpl", ".jss"}

ALL_MEDIA_EXT = VIDEO_EXT | AUDIO_EXT | IMAGE_EXT | MODEL_EXT

KIND_VIDEO = "video"
KIND_AUDIO = "audio"
KIND_IMAGE = "image"
KIND_MODEL = "model"


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def kind_of(path: str):
    e = ext_of(path)
    if e in VIDEO_EXT:
        return KIND_VIDEO
    if e in AUDIO_EXT:
        return KIND_AUDIO
    if e in IMAGE_EXT:
        return KIND_IMAGE
    if e in MODEL_EXT:
        return KIND_MODEL
    return None


def is_media(path: str) -> bool:
    return ext_of(path) in ALL_MEDIA_EXT


def dialog_filter(tr) -> str:
    def pat(exts):
        return " ".join("*" + e for e in sorted(exts))
    return ";;".join([
        f"{tr('all_media')} ({pat(ALL_MEDIA_EXT)})",
        f"{tr('videos')} ({pat(VIDEO_EXT)})",
        f"{tr('music')} ({pat(AUDIO_EXT)})",
        f"{tr('images')} ({pat(IMAGE_EXT)})",
        f"{tr('models')} ({pat(MODEL_EXT)})",
        f"{tr('all_files')} (*.*)",
    ])
