"""Engine constants shared across several submodules."""

from __future__ import annotations

import re

UA = "Mozilla/5.0 (compatible; Glaneur/1.0)"

SIZE_SUFFIX = re.compile(r"-\d{2,5}x\d{2,5}(?=\.[A-Za-z]{3,4}$)")
