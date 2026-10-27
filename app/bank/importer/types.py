"""Types for non-schema workflow records. Portable question/source shapes use JSON Schema."""
from typing import Dict,List,Literal,NotRequired,TypedDict
from ..format import Material

class Repair(TypedDict):
    source_fingerprint:str
    question:NotRequired[Material]
    answer:NotRequired[dict]
    marks:NotRequired[int]
    topics:NotRequired[List[str]]
    reason:NotRequired[str]

class PairReport(TypedDict,total=False):
    pair:str
    status:Literal['quarantined']
    source_fingerprint:str
    cache_hit:bool
    detected_questions:int
    detected_answers:int
    accepted:int
    quarantined:int
    missing_questions:List[int]
    missing_answers:List[int]
    qp_marks:int
    ms_marks:int
    issues:List[str]

class ImportReport(TypedDict):
    parser_version:str
    base_revision:str
    revision:str
    files_failed:List[dict]
    duplicate_files:int
    pairs:List[PairReport]
    accepted:int
    quarantined:int
    total_questions:int
    elapsed_seconds:float
    review_claim:str
