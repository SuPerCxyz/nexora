"""Snapshot write-domain errors."""


class SnapshotChangeError(RuntimeError):
    pass


class SnapshotChangeConflict(SnapshotChangeError):
    pass
