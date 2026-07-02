# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

"""``python -m bench.perception`` entry point — thin delegate to bench.main().

Keeps the runnable surface (acceptance §4: ``python -m bench.perception``)
separate from the implementation in :mod:`bench.perception.bench`.
"""

import sys

from bench.perception.bench import main

raise SystemExit(main(sys.argv[1:]))
