"""A teaching judgment is bound to both sources and ALL material, including shared diagrams."""
import hashlib,json
from typing import TypedDict,NotRequired
from ..format import COORDINATES

class Decision(TypedDict):
    fingerprint:str
    required_chapters:list[int]
    evidence:list[dict]
    issues:NotRequired[list[str]]
    prerequisites:NotRequired[list[str]]


def fingerprint(question,source_map):
    value=['teaching-material-v2',COORDINATES,source_map[question['question']['source_id']]['sha256'],source_map[question['answer']['source_id']]['sha256'],question['original_question_number'],question['question']['regions'],question['answer']['regions']]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
