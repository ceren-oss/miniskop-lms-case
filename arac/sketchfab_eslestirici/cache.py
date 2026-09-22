"""Diske yazan basit JSON onbellegi.

Amac: calistirma yarida kesilirse ayni istekler tekrar yapilmasin. Her kayit
ayri bir dosyadir; boylece elle incelenebilir ve tek bir bozuk kayit digerlerini
etkilemez.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class Onbellek:
    def __init__(self, kok: Path, omur_gun: float | None = None) -> None:
        self.kok = Path(kok)
        self.omur_gun = omur_gun
        self.kok.mkdir(parents=True, exist_ok=True)
        self.isabet = 0
        self.kacik = 0

    @staticmethod
    def anahtar(*parcalar: Any) -> str:
        ham = json.dumps(parcalar, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(ham.encode("utf-8")).hexdigest()[:32]

    def _yol(self, bolum: str, anahtar: str) -> Path:
        dizin = self.kok / bolum
        dizin.mkdir(parents=True, exist_ok=True)
        return dizin / f"{anahtar}.json"

    def oku(self, bolum: str, anahtar: str) -> Any | None:
        yol = self._yol(bolum, anahtar)
        if not yol.exists():
            self.kacik += 1
            return None
        try:
            kayit = json.loads(yol.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Bozuk kaydi sessizce atla; yeniden uretilecek.
            self.kacik += 1
            return None
        if self.omur_gun is not None:
            yas = time.time() - kayit.get("_zaman", 0)
            if yas > self.omur_gun * 86400:
                self.kacik += 1
                return None
        self.isabet += 1
        return kayit.get("veri")

    def yaz(self, bolum: str, anahtar: str, veri: Any, etiket: str = "") -> None:
        kayit = {"_zaman": time.time(), "_etiket": etiket, "veri": veri}
        yol = self._yol(bolum, anahtar)
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(
            json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        gecici.replace(yol)  # atomik: yarim dosya kalmaz

    def ozet(self) -> str:
        return f"onbellek: {self.isabet} isabet / {self.kacik} yeni"
