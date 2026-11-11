"""SeekSync: watch SoundCloud channels, fetch new releases from Soulseek."""
__version__ = "0.6.5"

from .net import use_bundled_certificates as _use_bundled_certificates

_use_bundled_certificates()      # before anything opens an HTTPS connection (see net.py)
