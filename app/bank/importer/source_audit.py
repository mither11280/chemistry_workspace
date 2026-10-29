"""Source-backed physical pagination audit; never waive missing-page gates."""
import re
from pathlib import Path
from typing import TypedDict
import fitz
from ..format import sha256
from ..pdf_layout import layout_page


class PaginationAudit(TypedDict):
    source_id: str
    sha256: str
    physical_pages: int
    declared_pages: int | None
    page_tree_count: int | None
    repaired_on_open: bool
    printed_page_numbers: list[dict]
    missing_printed_pages: list[int]
    issues: list[str]
    conclusion: str


def audit_pagination(path: Path, source: dict) -> PaginationAudit:
    digest = sha256(path)
    if digest != source['sha256']:
        raise ValueError('Registered source hash mismatch: ' + source['source_id'])
    with fitz.open(path) as doc:
        cover = layout_page(doc, 0).get_text()
        match = re.search(r'document\s+(?:has|consists\s+of)\s*(\d+)\s*(?:printed\s+)?pages', cover, re.I)
        blanks = re.search(r'printed pages and (\d+) blank pages?', cover, re.I)
        declared = int(match[1]) + (int(blanks[1]) if blanks else 0) if match else None
        page_root = doc.xref_get_key(doc.pdf_catalog(), 'Pages')
        tree_count = None
        if page_root[0] == 'xref':
            count = doc.xref_get_key(int(page_root[1].split()[0]), 'Count')
            if count[0] == 'int':
                tree_count = int(count[1])
        labels = []
        for pi in range(1, len(doc)):
            page = layout_page(doc, pi)
            words = [w for w in page.get_text('words')
                     if re.fullmatch(r'\d{1,3}', w[4])
                     and page.rect.width * .42 < w[0] < page.rect.width * .58
                     and 10 < w[1] < page.rect.height * .08]
            # The highest numeric baseline is the page header, not a number
            # in a task on the next line. Ambiguity on that baseline stays open.
            highest = min((w[1] for w in words), default=0)
            candidates = sorted({int(w[4]) for w in words if w[1] < highest + 2})
            labels.append({'page_index': pi, 'printed_page_number': candidates[0] if len(candidates) == 1 else None,
                           'candidates': candidates})
        seen = [1] + [row['printed_page_number'] for row in labels if row['printed_page_number'] is not None]
        missing = sorted(set(range(1, declared + 1)) - set(seen)) if declared else []
        issues = []
        if doc.is_repaired:
            issues.append('pdf_repaired_on_open')
        if tree_count != len(doc):
            issues.append('page_tree_count_disagrees_with_reader')
        if declared is not None and declared != len(doc):
            issues.append('physical_page_count_mismatch')
        if len(seen) != len(set(seen)):
            issues.append('duplicate_printed_page_number')
        if any(row['printed_page_number'] is None for row in labels):
            issues.append('unreadable_or_ambiguous_printed_page_header')
        if missing:
            issues.append('declared_printed_pages_not_found')
        return dict(source_id=source['source_id'], sha256=digest, physical_pages=len(doc),
                    declared_pages=declared, page_tree_count=tree_count,
                    repaired_on_open=bool(doc.is_repaired), printed_page_numbers=labels,
                    missing_printed_pages=missing, issues=issues,
                    conclusion='incomplete-physical-source-not-parser-count-error'
                    if declared and declared != len(doc) and tree_count == len(doc) and not doc.is_repaired
                    else 'requires-investigation' if issues else 'pagination-consistent-not-semantic-acceptance')
