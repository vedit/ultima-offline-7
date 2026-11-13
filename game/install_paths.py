"""Locate tracked sources and the player's private Windows installation."""
import os
from pathlib import Path

GAME_SOURCE = Path(__file__).resolve().parent
INSTALL = Path(os.environ.get("ULTIMA_OFFLINE_HOME", "E:/UltimaOffline")).resolve()
RUNTIME = INSTALL / "PoCs" / "ClassicUO-U7-Local"
ATLAS_OUTPUT = RUNTIME / "reviewed-atlas"
EARLIER_ATLAS = INSTALL / "PoCs" / "Trinsic-Asset-Mapping" / "atlas"
