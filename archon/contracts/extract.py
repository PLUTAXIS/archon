from typing import Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

Visibility = Literal["visible", "hidden", "veryHidden"]
SourceFormat = Literal["xlsx", "xlsm", "xlsb", "accdb"]
DataType = Literal["n", "s", "b", "e", "d"]

ExceptionCode = Literal[
    "E_PASSWORD_PROTECTED",
    "E_VBA_LOCKED",
    "E_VERY_HIDDEN_SHEET",
    "E_CORRUPT_ZIP",
    "E_PARTIAL_SHEET_RECOVERY",
    "E_EXTERNAL_LINK_UNRESOLVED",
    "E_UNSUPPORTED_FEATURE",
    "E_OLE_PARSE_FAILED",
]
Severity = Literal["warn", "error"]


class Source(BaseModel):
    model_config = {"extra": "forbid"}
    filename: str
    sha256: str
    format: SourceFormat
    bytes: Annotated[int, Field(ge=0)]


class Sheet(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    index: Annotated[int, Field(ge=0)]
    visibility: Visibility
    dimensions: str
    merged_cells: list[str] = Field(default_factory=list)
    frozen_panes: str | None = None


class Cell(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}
    sheet: str
    address: str = Field(pattern=r"^[A-Z]{1,3}\d{1,7}$")
    row: Annotated[int, Field(ge=1)]
    col: Annotated[int, Field(ge=1)]
    formula: str | None = None  # WITH leading '='
    cached_value: float | str | bool | None = None
    data_type: DataType
    number_format: str | None = None
    is_array_formula: bool = False
    shared_group_id: int | None = None

    @field_validator("formula")
    @classmethod
    def must_keep_equals(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith("="):
            raise ValueError("formula must retain its leading '='")
        return v


class DefinedName(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    scope: str
    refers_to: str


class Table(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    sheet: str
    ref: str
    is_hidden: bool = False


class ExternalLink(BaseModel):
    model_config = {"extra": "forbid"}
    index: int
    target: str
    resolved: bool


class VbaModule(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    type: Literal["standard", "class", "sheet", "thisworkbook"]
    source: str
    sha256: str
    line_count: Annotated[int, Field(ge=0)]


class ExtractException(BaseModel):
    model_config = {"extra": "forbid"}
    code: ExceptionCode
    severity: Severity
    sheet: str | None = None
    detail: str


class RawExtract(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: Literal["1.0"]
    workbook_id: UUID
    source: Source
    sheets: list[Sheet]
    cells: list[Cell]
    defined_names: list[DefinedName] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    external_links: list[ExternalLink] = Field(default_factory=list)
    vba_modules: list[VbaModule] = Field(default_factory=list)
    exceptions: list[ExtractException]  # NO default — must be passed explicitly