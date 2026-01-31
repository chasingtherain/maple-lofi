# ADR 002: Dataclass for Configuration Instead of Dict or Class

**Date**: 2025-01-15
**Status**: Accepted
**Decision makers**: Project architect
**Tags**: configuration, type-safety, maintainability

## Context

The pipeline needs configuration that flows through all stages:
- Input/output directories
- Optional asset paths (cover, texture, drums)
- Audio processing parameters (crossfade duration, EQ frequencies, gains)
- Behavior flags (skip_lofi)
- Run metadata (run_id, timestamp)

We need a way to:
- Store these ~15 configuration parameters
- Pass them to all stages
- Ensure type safety
- Provide sensible defaults
- Make it easy to add new parameters

## Problem

How should we represent pipeline configuration in code?

## Options Considered

### Option 1: Dictionary

```python
config = {
    'input_dir': Path('input'),
    'output_dir': Path('output'),
    'fade_ms': 15000,
    'highpass_hz': 35,
    # ... 10 more keys
}

# Usage
def merge_stage(tracks, config, logger):
    crossfade_ms = config['fade_ms']  # ❌ Typo = KeyError at runtime
```

**Pros**:
- Familiar (everyone knows dicts)
- Flexible (add keys anytime)
- Serializable (json.dumps works)

**Cons**:
- **No type checking**: Can't catch typos until runtime
- **No autocomplete**: IDE doesn't know what keys exist
- **No defaults**: Must set every key manually
- **No validation**: Can put any value in any key
- **Hard to discover**: What keys are valid? Need to read docs

### Option 2: Regular Class

```python
class PipelineConfig:
    def __init__(self, input_dir, output_dir, fade_ms=15000, ...):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.fade_ms = fade_ms
        # ... 12 more lines

# Usage
config = PipelineConfig(
    input_dir=Path('input'),
    output_dir=Path('output')
)
```

**Pros**:
- Type hints possible (self.fade_ms: int)
- Autocomplete works
- Can add validation in `__init__`
- Defaults via default arguments

**Cons**:
- **Boilerplate**: Need to write `self.x = x` for every parameter
- **Mutable**: Can do `config.fade_ms = -999` later (unexpected changes)
- **No `__repr__`**: Debugging shows `<PipelineConfig object at 0x...>`
- **No equality**: Can't compare configs with `==`
- **Manual serialization**: Need to write `to_dict()` method

### Option 3: Named Tuple

```python
from typing import NamedTuple

class PipelineConfig(NamedTuple):
    input_dir: Path
    output_dir: Path
    fade_ms: int = 15000
    highpass_hz: int = 35
    # ...
```

**Pros**:
- Immutable (can't change after creation)
- Type hints built-in
- Autocomplete works
- `__repr__` and `==` for free
- No boilerplate

**Cons**:
- **Positional arguments**: Must remember order (error-prone)
  ```python
  # Hard to read
  config = PipelineConfig(Path('in'), Path('out'), 15000, 35, 11000, ...)
  ```
- **Can't add methods**: NamedTuples are for data only
- **No post-init validation**: Can't check constraints after creation

### Option 4: Dataclass (Chosen)

```python
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

@dataclass
class PipelineConfig:
    # Required
    input_dir: Path
    output_dir: Path

    # Optional assets
    cover_image: Path | None = None
    texture: Path | None = None
    drums: Path | None = None

    # Audio parameters (with defaults)
    fade_ms: int = 15000
    highpass_hz: int = 35
    lowpass_hz: int = 11000
    texture_gain_db: float = -26.0
    drums_gain_db: float = -22.0
    drums_start_s: float = 0.0

    # Behavior
    skip_lofi: bool = False

    # Metadata (generated)
    run_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Usage
config = PipelineConfig(
    input_dir=Path('input'),
    output_dir=Path('output'),
    fade_ms=5000  # Override default
)

# Autocomplete works
print(config.fade_ms)  # ✅ IDE knows this exists

# Type checking works
config.fade_ms = "not a number"  # ❌ Caught by mypy/pyright

# Debugging is easy
print(config)
# PipelineConfig(input_dir=Path('input'), output_dir=Path('output'), fade_ms=5000, ...)
```

**Pros**:
- **Type safety**: IDE and type checkers catch errors
- **Autocomplete**: IDE shows all available fields
- **Defaults built-in**: Don't need to specify every parameter
- **Immutable (frozen)**: Can make immutable with `@dataclass(frozen=True)`
- **Good repr**: Shows all values when printed
- **Equality**: Can compare with `==`
- **Can add methods**: Can define `def validate(self)`, etc.
- **Field factories**: Can generate run_id, timestamp automatically

**Cons**:
- Requires Python 3.7+ (we require 3.10+, so fine)
- Slightly more imports (but stdlib only)

## Decision

**We will use `@dataclass` for PipelineConfig.**

### Implementation

```python
# maple_lofi/config.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class PipelineConfig:
    """Pipeline configuration with sensible defaults.

    Required:
        input_dir: Directory containing audio files
        output_dir: Directory for output files (created if needed)

    Optional assets:
        cover_image: Cover image for video (triggers Stage 4)
        texture: Rain/texture audio (mixed in Stage 3)
        drums: Drum loop audio (mixed in Stage 3)

    Audio parameters:
        fade_ms: Crossfade duration in milliseconds (default: 15000)
        highpass_hz: Highpass filter frequency (default: 35)
        lowpass_hz: Lowpass filter frequency (default: 11000)
        texture_gain_db: Texture gain in dB (default: -26.0)
        drums_gain_db: Drums gain in dB (default: -22.0)
        drums_start_s: Drums start time in seconds (default: 0.0)

    Behavior:
        skip_lofi: Skip Stage 3 (lofi processing)

    Metadata (auto-generated):
        run_id: Unique identifier for this run (UUID)
        timestamp: ISO 8601 timestamp of run start
    """

    # Required
    input_dir: Path
    output_dir: Path

    # Optional assets
    cover_image: Path | None = None
    texture: Path | None = None
    drums: Path | None = None

    # Audio parameters
    fade_ms: int = 15000
    highpass_hz: int = 35
    lowpass_hz: int = 11000
    texture_gain_db: float = -26.0
    drums_gain_db: float = -22.0
    drums_start_s: float = 0.0

    # Behavior
    skip_lofi: bool = False

    # Metadata
    run_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

### Usage in CLI

```python
# maple_lofi/cli.py

def build_config(args: argparse.Namespace) -> PipelineConfig:
    """Convert CLI args to PipelineConfig."""
    return PipelineConfig(
        input_dir=args.input.resolve(),
        output_dir=args.output.resolve(),
        cover_image=args.cover.resolve() if args.cover else None,
        texture=args.texture.resolve() if args.texture else None,
        drums=args.drums.resolve() if args.drums else None,
        fade_ms=args.fade_ms,
        highpass_hz=args.highpass,
        lowpass_hz=args.lowpass,
        texture_gain_db=args.texture_gain,
        drums_gain_db=args.drums_gain,
        drums_start_s=args.drums_start,
        skip_lofi=args.skip_lofi
    )
```

### Usage in Stages

```python
# maple_lofi/stages/merge.py

def merge_stage(tracks: List[AudioTrack], config: PipelineConfig, logger: Logger) -> Path:
    """Merge tracks with crossfades."""

    # Autocomplete works - IDE shows all config fields
    crossfade_ms = config.fade_ms

    # Type checker ensures we're using int (not string)
    crossfade_s = crossfade_ms / 1000.0

    # ...
```

## Rationale

### 1. Type Safety

**Problem**: Typos in dict keys cause runtime errors.

**Solution**: Dataclass fields are checked by IDE and type checkers:

```python
# Dict - no error until runtime
config['fade_mss'] = 15000  # ❌ Typo, KeyError later

# Dataclass - error at development time
config.fade_mss = 15000  # ❌ IDE highlights error immediately
```

### 2. Autocomplete

**Problem**: With dicts, you need to remember or look up key names.

**Solution**: IDE autocomplete shows all available fields:

```python
# Type "config." and IDE shows:
# - input_dir
# - output_dir
# - fade_ms
# - highpass_hz
# ... all fields
```

This **speeds up development** and **reduces errors**.

### 3. Self-Documenting

**Problem**: What parameters are available? What are the defaults?

**Solution**: Dataclass definition is the documentation:

```python
@dataclass
class PipelineConfig:
    fade_ms: int = 15000  # ← Default is visible here
```

Junior engineers can read one file (`config.py`) to see all options.

### 4. Generated Fields

**Problem**: Need to generate run_id and timestamp for every run.

**Solution**: Use `field(default_factory=...)`:

```python
run_id: str = field(default_factory=lambda: str(uuid4()))
```

This runs **once per instance**, so each config gets a unique ID automatically.

### 5. Defaults Without Boilerplate

**Problem**: Regular classes require writing defaults twice:

```python
class Config:
    def __init__(self, fade_ms=15000):  # ← Default here
        self.fade_ms = fade_ms           # ← Boilerplate

    fade_ms: int = 15000  # ← And again for type hint?
```

**Solution**: Dataclass unifies these:

```python
@dataclass
class Config:
    fade_ms: int = 15000  # ← One line, type + default
```

## Consequences

### Positive

- **Type safety**: Catch errors before runtime (with mypy/pyright)
- **Autocomplete**: Faster development, fewer typos
- **Self-documenting**: All fields visible in one place
- **Less boilerplate**: No `self.x = x` repetition
- **Better debugging**: `print(config)` shows all values
- **Equality**: Can compare configs with `==`
- **Immutable option**: Can use `@dataclass(frozen=True)` if needed

### Negative

- **Python 3.7+ required**: (We require 3.10+, so not an issue)
- **Slight learning curve**: Junior engineers may not know dataclasses yet
  - *Mitigation*: Simple concept, easy to learn, add docs

### Neutral

- **Not serializable by default**: Can't `json.dumps(config)` directly
  - *Mitigation*: Not needed (we build manifest separately)
  - *Alternative*: Could add `to_dict()` method if needed

## Implementation Guidelines

### For Junior Engineers

When adding a new configuration parameter:

1. **Add field to PipelineConfig dataclass** with type hint and default:
   ```python
   new_param: int = 42  # Add here
   ```

2. **Update CLI** to accept new argument:
   ```python
   parser.add_argument('--new-param', type=int, default=42)
   ```

3. **Pass to config builder**:
   ```python
   PipelineConfig(..., new_param=args.new_param)
   ```

4. **Use in stages**:
   ```python
   value = config.new_param  # Autocomplete works!
   ```

### When to Use Dataclasses

✅ **Use dataclasses when**:
- You have multiple related configuration values
- You want type safety and autocomplete
- Values should be immutable (use `frozen=True`)
- You need defaults for some fields
- You want good `__repr__` for debugging

❌ **Don't use dataclasses when**:
- You have only 1-2 values (just use function parameters)
- Schema changes frequently (dynamic keys - use dict)
- You need custom getters/setters (use `@property` in regular class)

## Examples from Standard Library

Dataclasses are used throughout Python's stdlib:

### pathlib.Path

Internally uses a similar pattern (pre-dataclasses):

```python
path = Path('/foo/bar')
print(path.parent)  # Autocomplete works
```

### typing.NamedTuple

The predecessor to dataclasses:

```python
class Point(NamedTuple):
    x: int
    y: int
```

Dataclasses are more flexible (mutable, methods, defaults).

## Alternatives for Specific Use Cases

### For Simple Data Transfer

If you just need to pass 2-3 values and don't need defaults:

```python
# Simple tuple unpacking
input_dir, output_dir = parse_args()
```

### For Complex Validation

If you need to validate relationships between fields:

```python
@dataclass
class PipelineConfig:
    fade_ms: int = 15000

    def __post_init__(self):
        """Validate after initialization."""
        if self.fade_ms < 0:
            raise ValueError("fade_ms must be positive")
        if self.highpass_hz >= self.lowpass_hz:
            raise ValueError("highpass must be less than lowpass")
```

### For External Config Files

If you load from YAML/JSON:

```python
# Load dict from file
with open('config.yaml') as f:
    data = yaml.safe_load(f)

# Convert to dataclass
config = PipelineConfig(**data)  # ✅ Validates types
```

## Related Decisions

- [ADR 001: Pipeline Architecture](001-pipeline-architecture.md) - Config flows through all stages
- [ADR 003: Manifest Format](003-manifest-format.md) - Config is serialized to manifest

## References

- PEP 557 (Data Classes): https://peps.python.org/pep-0557/
- Python dataclasses docs: https://docs.python.org/3/library/dataclasses.html
- Real Python dataclasses guide: https://realpython.com/python-data-classes/

## Review History

- **2025-01-15**: Initial decision (approved)

---

**Key Takeaway for Junior Engineers**: When you have multiple related configuration values, use a `@dataclass` instead of a dict or regular class. You get type safety, autocomplete, and defaults with minimal boilerplate. This prevents bugs and speeds up development.
