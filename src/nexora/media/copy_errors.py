"""Media image copy domain errors."""


class MediaCopyError(RuntimeError):
    pass


class MediaCopyCancelled(MediaCopyError):
    pass
