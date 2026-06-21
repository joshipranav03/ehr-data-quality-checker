"""Ingestion adapters: convert healthcare interchange formats into the flat
tabular DataFrames the quality engine validates.

* :mod:`app.ingest.fhir`   — HL7 FHIR R4 Bundles (e.g. Synthea output)
* :mod:`app.ingest.hl7v2`  — HL7 v2 ADT messages (pipe-delimited)
"""

from .fhir import ingest_fhir_bundle, FhirIngestError  # noqa: F401
from .hl7v2 import ingest_hl7v2, Hl7IngestError  # noqa: F401
