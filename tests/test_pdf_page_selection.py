from __future__ import annotations

import pytest


def test_parse_page_spec_supports_ranges_and_dedupes(cli_module):
    assert cli_module.parse_page_spec("3,1,2-4,4", 5) == [1, 2, 3, 4]


def test_parse_page_spec_rejects_out_of_bounds_page(cli_module):
    with pytest.raises(cli_module.CLIError, match="exceeds document page count"):
        cli_module.parse_page_spec("1,6", 5)


def test_parse_page_spec_rejects_invalid_range(cli_module):
    with pytest.raises(cli_module.CLIError, match="Invalid page range"):
        cli_module.parse_page_spec("4-2", 5)
