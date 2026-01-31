# ADR 003: FFmpeg Abstraction Layer

**Date**: 2025-01-15
**Status**: Accepted
**Decision makers**: Project architect
**Tags**: abstraction, separation-of-concerns, testability

## Context

The pipeline uses FFmpeg heavily:
- Stage 1: `ffprobe` to get audio metadata
- Stage 2: `ffmpeg` to merge tracks with crossfades
- Stage 3: `ffmpeg` to apply lofi effects
- Stage 4: `ffmpeg` to render video

Each stage needs to:
- Build FFmpeg commands (complex filter graphs)
- Execute commands via subprocess
- Handle errors
- Log commands for debugging

We need to decide how to organize this FFmpeg-related code.

## Problem

Where should FFmpeg command construction and execution logic live?

## Options Considered

### Option 1: Inline in Each Stage

Put FFmpeg commands directly in stage functions:

```python
# maple_lofi/stages/merge.py

def merge_stage(tracks, config, logger):
    # Build command inline
    cmd = ["ffmpeg"]
    for track in tracks:
        cmd.extend(["-i", str(track.path)])

    filter_parts = []
    for i in range(len(tracks)):
        filter_parts.append(f"[{i}:a]loudnorm[norm{i}]")

    # ... 30 more lines of filter construction

    cmd.extend(["-filter_complex", ";".join(filter_parts)])
    cmd.extend(["-ar", "48000", "-ac", "2", "-y", str(output)])

    # Execute inline
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ProcessingError(f"FFmpeg failed: {result.stderr}")

    return output
```

**Pros**:
- All logic in one place
- No need to navigate to other files

**Cons**:
- **Hard to test**: Can't test command construction without executing
- **Duplication**: Every stage repeats subprocess.run logic
- **Hard to read**: Mixing business logic (what to do) with technical details (how to call FFmpeg)
- **Hard to debug**: Can't easily see what command was run
- **Inconsistent error handling**: Each stage may handle errors differently

### Option 2: Utility Functions in Each Stage File

Create helper functions at the bottom of each stage file:

```python
# maple_lofi/stages/merge.py

def merge_stage(tracks, config, logger):
    cmd = _build_merge_command(tracks, config)
    _run_ffmpeg(cmd, logger)
    return output

def _build_merge_command(tracks, config):
    # ... command construction
    return cmd

def _run_ffmpeg(cmd, logger):
    # ... subprocess execution
    pass
```

**Pros**:
- Separates construction from execution
- Can test _build_merge_command without executing

**Cons**:
- **Duplication**: _run_ffmpeg repeated in every stage file
- **Inconsistent**: Each stage may implement differently
- **No reuse**: Can't reuse probing logic across stages

### Option 3: Dedicated FFmpeg Module (Chosen)

Create a separate module for all FFmpeg operations:

```
maple_lofi/
├── ffmpeg/
│   ├── __init__.py
│   ├── commands.py    # Command builders
│   ├── executor.py    # Subprocess wrapper
│   └── probe.py       # ffprobe metadata extraction
```

```python
# maple_lofi/ffmpeg/commands.py

def build_merge_command(
    tracks: List[AudioTrack],
    crossfade_durations: List[float],
    output_path: Path
) -> List[str]:
    """Build FFmpeg command for merging with crossfades.

    Returns:
        FFmpeg command as list of strings (ready for subprocess)
    """
    cmd = ["ffmpeg"]

    # Add inputs
    for track in tracks:
        cmd.extend(["-i", str(track.path)])

    # Build filter graph
    # ... (complex logic isolated here)

    return cmd


# maple_lofi/ffmpeg/executor.py

def run_ffmpeg(
    command: List[str],
    logger: Logger,
    description: str = "FFmpeg operation",
    timeout: int | None = None
) -> None:
    """Execute FFmpeg command with logging and error handling.

    Args:
        command: FFmpeg command as list
        logger: Logger instance
        description: Human-readable description
        timeout: Optional timeout in seconds

    Raises:
        ProcessingError: If FFmpeg fails
    """
    logger.info(f"Running {description}...")
    logger.debug(f"Command: {' '.join(command)}")

    start_time = time.time()
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    duration = time.time() - start_time

    if result.returncode != 0:
        logger.error(f"FFmpeg failed (exit code {result.returncode})")
        logger.error(f"stderr: {result.stderr}")
        raise ProcessingError(f"{description} failed: {result.stderr}")

    logger.info(f"  ✓ Completed in {duration:.1f}s")


# Usage in stages

from maple_lofi.ffmpeg.commands import build_merge_command
from maple_lofi.ffmpeg.executor import run_ffmpeg

def merge_stage(tracks, config, logger):
    cmd = build_merge_command(tracks, crossfade_durations, output)
    run_ffmpeg(cmd, logger, description="Crossfade merging")
    return output
```

**Pros**:
- **Separation of concerns**: Stages focus on *what*, FFmpeg module on *how*
- **Reusable**: run_ffmpeg used by all stages (consistent error handling)
- **Testable**: Can test command construction without execution
- **Debuggable**: All FFmpeg logic in one place
- **Loggable**: Centralized logging of all commands
- **Maintainable**: Change FFmpeg behavior once, affects all stages

**Cons**:
- More files (but better organized)
- Need to import from ffmpeg module

## Decision

**We will use Option 3: Dedicated FFmpeg module with separation between command construction and execution.**

### Structure

```
maple_lofi/ffmpeg/
├── __init__.py
├── commands.py       # Pure functions that build FFmpeg commands
├── executor.py       # run_ffmpeg() - subprocess wrapper with logging
└── probe.py          # probe_audio_file() - ffprobe metadata extraction
```

### Design Principles

#### 1. Command Builders Return Lists (Not Strings)

```python
# ✅ Good - safe from injection
def build_merge_command(...) -> List[str]:
    return ["ffmpeg", "-i", user_input, "-y", "output.wav"]

# ❌ Bad - shell injection risk
def build_merge_command(...) -> str:
    return f"ffmpeg -i {user_input} -y output.wav"
```

#### 2. Command Builders Are Pure Functions

```python
# ✅ Good - no side effects, easy to test
def build_merge_command(tracks, durations, output) -> List[str]:
    cmd = ["ffmpeg"]
    # ... build command
    return cmd

# ❌ Bad - has side effects
def build_merge_command(tracks, durations, output):
    cmd = ["ffmpeg"]
    # ... build command
    subprocess.run(cmd)  # ❌ Side effect
```

#### 3. Executor Handles All Subprocess Logic

```python
def run_ffmpeg(command, logger, description, timeout=None):
    """Single place for all subprocess logic."""
    # - Log command before execution
    # - Execute with timeout
    # - Capture output
    # - Parse errors
    # - Raise consistent exceptions
```

## Rationale

### 1. Testability

**Problem**: Can't test FFmpeg command construction without executing.

**Solution**: Test command builders as pure functions:

```python
# test/test_ffmpeg_commands.py

def test_build_merge_command():
    track1 = AudioTrack(path=Path("t1.mp3"), duration_s=30, ...)
    track2 = AudioTrack(path=Path("t2.mp3"), duration_s=30, ...)

    cmd = build_merge_command([track1, track2], [15.0], Path("out.wav"))

    # Verify command structure
    assert cmd[0] == "ffmpeg"
    assert "-i" in cmd
    assert "t1.mp3" in " ".join(cmd)
    assert "acrossfade" in " ".join(cmd)
    assert "-ar" in cmd
    assert "48000" in cmd
```

No need to actually run FFmpeg!

### 2. Consistency

**Problem**: Each stage handles FFmpeg errors differently.

**Solution**: Centralized error handling in run_ffmpeg():

```python
def run_ffmpeg(command, logger, description, timeout):
    # All stages get same error handling:
    # - Timeout handling
    # - Exit code checking
    # - stderr parsing
    # - Consistent exception type (ProcessingError)
```

### 3. Debuggability

**Problem**: Hard to see what FFmpeg command was executed.

**Solution**: Log all commands in one place:

```python
def run_ffmpeg(command, logger, ...):
    # Always log full command
    logger.info(f"Command: {' '.join(command)}")

    # User can copy-paste to test manually:
    # ffmpeg -i track1.mp3 -i track2.mp3 -filter_complex "..." -y out.wav
```

### 4. Maintainability

**Problem**: Need to change FFmpeg execution behavior (e.g., add progress parsing).

**Solution**: Change one function, affects all stages:

```python
def run_ffmpeg(command, logger, ...):
    # Add progress parsing here
    # All stages benefit automatically
```

### 5. Separation of Concerns

**Stages** focus on business logic:
- *What* to process
- *When* to call FFmpeg
- *What* to do with the result

**FFmpeg module** focuses on technical details:
- *How* to build commands
- *How* to execute subprocess
- *How* to parse errors

## Consequences

### Positive

- **Easy to test**: Command builders are pure functions
- **Consistent**: All FFmpeg calls use same executor
- **Debuggable**: All commands logged in consistent format
- **Maintainable**: Change FFmpeg logic once
- **Reusable**: Probe, execute logic shared across stages
- **Safe**: List-based commands prevent injection

### Negative

- **More files**: 3 files (commands, executor, probe) vs inline
  - *Mitigation*: Better organization, worth it
- **Import overhead**: Stages need to import from ffmpeg module
  - *Mitigation*: Minimal, clear imports

### Neutral

- **Learning curve**: Junior engineers need to know where to find FFmpeg logic
  - *Mitigation*: Clear naming (ffmpeg/ directory), documented in architecture

## Implementation Guidelines

### For Junior Engineers

#### When to Add a New FFmpeg Operation

1. **Determine if it's a command builder or metadata extraction**:
   - Building command? → Add to `commands.py`
   - Getting metadata? → Add to `probe.py`

2. **Write as pure function**:
   ```python
   # commands.py
   def build_new_command(inputs, output_path) -> List[str]:
       """Build FFmpeg command for X.

       Args:
           inputs: What you need to build the command
           output_path: Where to write output

       Returns:
           FFmpeg command as list of strings
       """
       cmd = ["ffmpeg"]
       # ... build command
       return cmd
   ```

3. **Execute via run_ffmpeg()**:
   ```python
   # In stage
   from maple_lofi.ffmpeg.commands import build_new_command
   from maple_lofi.ffmpeg.executor import run_ffmpeg

   cmd = build_new_command(inputs, output)
   run_ffmpeg(cmd, logger, description="What this does")
   ```

4. **Write tests**:
   ```python
   # test/test_ffmpeg_commands.py
   def test_build_new_command():
       cmd = build_new_command(inputs, Path("out.wav"))
       assert cmd[0] == "ffmpeg"
       # ... more assertions
   ```

#### When NOT to Use This Pattern

❌ **Don't abstract if**:
- You're calling a different tool (not FFmpeg)
- You need very custom error handling (extend run_ffmpeg instead)

✅ **Do abstract if**:
- You're building any FFmpeg command
- You're executing any subprocess (could extend to other tools)

## Examples from Other Projects

### Django ORM

Separates query construction from execution:

```python
# Build query (pure function)
query = User.objects.filter(age__gt=18).order_by('name')

# Execute query (side effect)
users = list(query)
```

Similar to our command builders vs executor.

### SQLAlchemy

```python
# Build SQL command (declarative)
stmt = select(User).where(User.age > 18)

# Execute command (executor)
result = session.execute(stmt)
```

### Docker SDK

```python
# Build container config
config = {
    'image': 'python:3.10',
    'command': 'python app.py'
}

# Execute (create container)
container = client.containers.run(**config)
```

## Related Decisions

- [ADR 001: Pipeline Architecture](001-pipeline-architecture.md) - Stages call FFmpeg module
- [ADR 004: Error Handling Strategy](004-error-handling.md) - ProcessingError raised by executor

## References

- Separation of Concerns: https://en.wikipedia.org/wiki/Separation_of_concerns
- Command Pattern: https://refactoring.guru/design-patterns/command
- Humble Object Pattern: https://martinfowler.com/bliki/HumbleObject.html

## Review History

- **2025-01-15**: Initial decision (approved)

---

**Key Takeaway for Junior Engineers**: When you have complex external tool interaction (like FFmpeg), **separate command construction from execution**. This makes your code:
1. **Testable** (test command building without executing)
2. **Consistent** (all executions use same error handling)
3. **Debuggable** (log all commands in one place)
4. **Maintainable** (change execution logic once, affects all callers)

This is an example of **Separation of Concerns** - each module has one job.
