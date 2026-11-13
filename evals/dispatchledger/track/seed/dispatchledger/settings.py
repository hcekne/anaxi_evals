"""Process configuration from the environment."""

import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    external_url: str
    data_dir: Path
    public_url: str
    clock_file: Path | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        clock = os.environ.get("DISPATCHLEDGER_CLOCK_FILE")
        return cls(
            external_url=os.environ.get(
                "DISPATCHLEDGER_EXTERNAL_URL", "http://127.0.0.1:8765"
            ).rstrip("/"),
            data_dir=Path(os.environ.get("DISPATCHLEDGER_DATA_DIR", "data")),
            public_url=os.environ.get("DISPATCHLEDGER_PUBLIC_URL", "http://127.0.0.1:8000").rstrip(
                "/"
            ),
            clock_file=Path(clock) if clock else None,
        )

    def now(self) -> float:
        """Current time in Unix seconds: the clock file when one is configured."""
        if self.clock_file is not None:
            return float(self.clock_file.read_text().strip())
        return time.time()
