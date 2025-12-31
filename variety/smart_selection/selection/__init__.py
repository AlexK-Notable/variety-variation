# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Selection components for the Smart Selection Engine.

This package contains decomposed components from SmartSelector:
- CandidateProvider: Database queries for candidate images
- ConstraintApplier: Color and dimension filtering
- SelectionEngine: Weighted random selection algorithm
"""

from variety.smart_selection.selection.candidates import (
    CandidateQuery,
    CandidateProvider,
)
from variety.smart_selection.selection.constraints import (
    ColorConstraints,
    ConstraintApplier,
)
from variety.smart_selection.selection.engine import (
    ScoredCandidate,
    SelectionEngine,
)

__all__ = [
    'CandidateQuery',
    'CandidateProvider',
    'ColorConstraints',
    'ConstraintApplier',
    'ScoredCandidate',
    'SelectionEngine',
]
