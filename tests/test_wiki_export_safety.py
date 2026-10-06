from datetime import datetime
from pathlib import Path

import pytest

from ax_starter.common import AXError, Purpose
from ax_starter.retrieval import Answer
from ax_starter.wiki_contracts import WikiCompilation, WikiCompileRequest
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


@pytest.mark.parametrize(
    "body",
    [
        "![pixel][remote]\n\n[remote]: https://attacker.example/pixel.png",
        "![pixel](<https://attacker.example/pixel.png>)",
        "![pixel](//attacker.example/pixel.png)",
        '<img src="https://attacker.example/pixel.png">',
    ],
)
def test_export_denies_image_syntax_and_html_before_downstream_render(
    tmp_path: Path, now: datetime, body: str
) -> None:
    # Given: malicious derived text remains review data; export must not ship an image fetch.
    service = wiki_service(tmp_path / "image.db", now)

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        return extractive_compiler(request, answer).model_copy(update={"body": body})

    draft = service.compile(wiki_author(), wiki_request(), now, compiler)
    _ = service.publish(wiki_reviewer(), draft.id, draft.payload_hash, now)
    # When / Then
    with pytest.raises(AXError, match="wiki_export_unsafe_markup"):
        _ = service.export(wiki_author(), draft.payload.page_id, Purpose.OPERATIONS, now)
