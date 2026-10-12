import pytest
from ai_service.patching import apply_edits, PatchError

HTML = '<!doctype html><html><head><title>unchanged</title></head><body><button id="go">Go</button><p id="out">0</p></body></html>'


def test_patch_changes_only_unique_anchors_without_cascading():
    result = apply_edits(
        HTML,
        {
            "edits": [
                {"old": 'id="go"', "new": 'data-testid="primary-action"'},
                {"old": '<p id="out">0</p>', "new": '<p data-testid="result">1</p>'},
            ]
        },
    )
    assert result == HTML.replace('id="go"', 'data-testid="primary-action"').replace(
        '<p id="out">0</p>', '<p data-testid="result">1</p>'
    )
    assert "<title>unchanged</title>" in result


@pytest.mark.parametrize(
    "edits",
    [
        [{"old": "missing", "new": "x"}],
        [{"old": "p", "new": "x"}],
        [{"old": "Go", "new": "Go"}],
        [
            {"old": '<button id="go">Go</button>', "new": "<button>Next</button>"},
            {"old": "Go", "new": "Next"},
        ],
        [{"old": "</html>", "new": ""}],
    ],
)
def test_invalid_patch_never_changes_original(edits):
    with pytest.raises(PatchError):
        apply_edits(HTML, {"edits": edits})


def test_new_text_cannot_be_used_as_a_later_anchor():
    with pytest.raises(PatchError):
        apply_edits(
            HTML,
            {"edits": [{"old": "Go", "new": "Next"}, {"old": "Next", "new": "Other"}]},
        )
