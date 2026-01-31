# ADR 001: Linear 4-Stage Pipeline Architecture

**Date**: 2025-01-15
**Status**: Accepted
**Decision makers**: Project architect
**Tags**: architecture, pipeline, modularity

## Context

We need to transform multiple audio files into a final video output through several processing steps:
1. Discover and order input files
2. Merge them with crossfades
3. Apply lofi effects
4. Render video with cover image

We need to decide how to structure this processing flow in code.

## Problem

How should we organize the code that performs these transformations?

Key considerations:
- **Maintainability**: Easy to understand and modify
- **Testability**: Can test each step independently
- **Debuggability**: Easy to isolate where failures occur
- **Extensibility**: Easy to add new processing steps
- **Error handling**: Clear failure points and recovery

## Options Considered

### Option 1: Monolithic Function

Put all logic in a single `process()` function:

```python
def process(input_dir, output_dir, config):
    # 200+ lines of code doing everything
    files = glob(...)
    merged = merge_audio(...)
    lofi = apply_effects(...)
    video = render_video(...)
    return video
```

**Pros**:
- Simple to understand (everything in one place)
- No need to pass data between functions
- Easy to share state

**Cons**:
- **Hard to test**: Can't test merge logic without running ingest
- **Hard to debug**: 200+ line function is difficult to reason about
- **Hard to extend**: Adding a new step requires editing massive function
- **Poor separation of concerns**: Mixing file I/O, audio processing, video rendering
- **Can't skip stages**: Must run everything or nothing

### Option 2: Class-Based Pipeline with Shared State

Create a `Pipeline` class with instance variables:

```python
class Pipeline:
    def __init__(self, config):
        self.config = config
        self.tracks = []
        self.merged_audio = None
        self.lofi_audio = None
        self.video = None

    def run(self):
        self.ingest()
        self.merge()
        self.lofi()
        self.video()

    def ingest(self):
        self.tracks = discover_files(self.config.input_dir)

    def merge(self):
        self.merged_audio = merge_tracks(self.tracks)

    # ... etc
```

**Pros**:
- Organized into methods (easier to navigate)
- Can test individual methods
- Easy to share state (instance variables)

**Cons**:
- **Implicit dependencies**: Methods depend on state set by previous methods
- **Hard to reason about**: What state does each method need? When was it set?
- **Testing complexity**: Must set up correct state before testing a method
- **Order matters**: Must call methods in correct sequence
- **Hidden mutations**: Methods mutate `self`, making data flow unclear

### Option 3: Event-Driven Architecture

Use an event bus to coordinate stages:

```python
class EventBus:
    def publish(self, event: Event):
        for handler in self.handlers[event.type]:
            handler(event)

bus = EventBus()
bus.on('files_discovered', merge_handler)
bus.on('merge_complete', lofi_handler)
bus.on('lofi_complete', video_handler)

bus.publish(FilesDiscoveredEvent(tracks))
```

**Pros**:
- Decoupled components
- Easy to add new handlers
- Async processing possible

**Cons**:
- **Overkill for linear flow**: We don't need decoupling (stages always run in order)
- **Hard to trace**: Data flow is indirect (events vs direct calls)
- **Complex error handling**: Where did the error occur? Which handler failed?
- **Testing overhead**: Need to set up event bus infrastructure

### Option 4: Linear Stage Functions (Chosen)

Each stage is a **pure function** that takes inputs and returns outputs:

```python
# Stage 1
def ingest_stage(config, logger) -> List[AudioTrack]:
    tracks = discover_files(config.input_dir)
    return tracks

# Stage 2
def merge_stage(tracks, config, logger) -> Path:
    merged_wav = merge_with_crossfades(tracks, config)
    return merged_wav

# Stage 3
def lofi_stage(input_wav, config, logger) -> Path:
    lofi_wav = apply_lofi_effects(input_wav, config)
    return lofi_wav

# Stage 4
def video_stage(audio, config, logger) -> Path:
    video_mp4 = render_video(audio, config)
    return video_mp4

# Orchestrator
class Pipeline:
    def run(self):
        tracks = ingest_stage(self.config, self.logger)
        merged = merge_stage(tracks, self.config, self.logger)
        lofi = lofi_stage(merged, self.config, self.logger)
        video = video_stage(lofi, self.config, self.logger)
```

**Pros**:
- **Explicit data flow**: Output of stage N is input to stage N+1
- **Easy to test**: Each stage is isolated (mock inputs, verify outputs)
- **Easy to skip stages**: Just don't call the function
- **Easy to debug**: Failure in stage N means look at stage N's code
- **Pure functions**: No side effects (besides file I/O), predictable behavior
- **Self-documenting**: Function signatures show exactly what data flows where

**Cons**:
- Need orchestrator to coordinate stages (minimal overhead)
- More files/modules (but better organization)

## Decision

**We will use Option 4: Linear stage functions coordinated by a Pipeline orchestrator.**

### Structure

```
maple_lofi/
├── pipeline.py           # Pipeline class (orchestrator)
├── stages/
│   ├── ingest.py         # Stage 1: def ingest_stage(...)
│   ├── merge.py          # Stage 2: def merge_stage(...)
│   ├── lofi.py           # Stage 3: def lofi_stage(...)
│   └── video.py          # Stage 4: def video_stage(...)
```

### Contract

Each stage function follows this contract:

```python
def stage_name(
    inputs: <stage-specific-type>,
    config: PipelineConfig,
    logger: Logger
) -> <stage-specific-output>:
    """
    Stage description.

    Args:
        inputs: What this stage needs (from previous stage)
        config: Immutable pipeline configuration
        logger: Logger instance for output

    Returns:
        What this stage produces (for next stage)

    Raises:
        ValidationError: Invalid inputs
        ProcessingError: Processing failed
    """
```

### Orchestration

The `Pipeline` class is a **thin orchestrator**:

```python
class Pipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.logger = setup_logger(config.output_dir / "run_log.txt")
        self.manifest = ManifestBuilder(config)

    def run(self) -> int:
        try:
            # Stage 1
            tracks = ingest_stage(self.config, self.logger)
            self.manifest.add_input_tracks(tracks)

            # Stage 2
            merged = merge_stage(tracks, self.config, self.logger)
            self.manifest.add_output("merged_clean", merged)

            # Stage 3 (optional)
            if not self.config.skip_lofi:
                lofi = lofi_stage(merged, self.config, self.logger)
                self.manifest.add_output("merged_lofi", lofi)

            # Stage 4 (optional)
            if self.config.cover_image:
                video = video_stage(lofi or merged, self.config, self.logger)
                self.manifest.add_output("final_video", video)

            # Write manifest
            self.manifest.write(self.config.output_dir / "manifest.json")

            return 0  # Success

        except ValidationError as e:
            self.logger.error(f"Validation error: {e}")
            return 1
        except ProcessingError as e:
            self.logger.error(f"Processing error: {e}")
            return 2
```

## Rationale

### 1. Explicit Data Flow

**Problem**: In class-based approach, it's unclear what data each method needs.

**Solution**: Function signatures make dependencies explicit:

```python
# Clear: merge needs tracks from ingest
def merge_stage(tracks: List[AudioTrack], ...) -> Path:
    pass

# Unclear: merge uses self.tracks (when was it set?)
def merge(self):
    use_tracks(self.tracks)
```

### 2. Testability

**Problem**: Testing a method in a class requires setting up state.

**Solution**: Test stages in isolation with mock inputs:

```python
def test_merge_stage():
    # Create test tracks (no need to run ingest)
    track1 = AudioTrack(path=Path("test1.mp3"), duration_s=30, ...)
    track2 = AudioTrack(path=Path("test2.mp3"), duration_s=30, ...)

    # Test merge in isolation
    output = merge_stage([track1, track2], config, logger)

    # Verify output
    assert output.exists()
    assert probe_audio_file(output).duration_s == pytest.approx(45, abs=1)
```

### 3. Debuggability

**Problem**: When pipeline fails, where is the bug?

**Solution**: Stack trace points directly to stage function:

```
Traceback (most recent call last):
  File "pipeline.py", line 45, in run
    lofi = lofi_stage(merged, self.config, self.logger)
  File "stages/lofi.py", line 78, in lofi_stage
    run_ffmpeg(command, logger)
  File "ffmpeg/executor.py", line 23, in run_ffmpeg
    raise ProcessingError("FFmpeg failed")
```

→ Bug is in `lofi_stage`, specifically in FFmpeg execution.

### 4. Optional Stages

**Problem**: Need to skip lofi processing or video rendering.

**Solution**: Conditional execution in orchestrator:

```python
# Skip lofi
if not self.config.skip_lofi:
    lofi = lofi_stage(merged, self.config, self.logger)

# Skip video (no cover image provided)
if self.config.cover_image:
    video = video_stage(audio, self.config, self.logger)
```

### 5. Single Responsibility

Each stage has **one job**:

- `ingest_stage`: Discover and order files
- `merge_stage`: Merge with crossfades
- `lofi_stage`: Apply lofi effects
- `video_stage`: Render video

This follows the **Single Responsibility Principle** from SOLID.

## Consequences

### Positive

- **Easy to understand**: Follow the data from stage 1 → 2 → 3 → 4
- **Easy to test**: Each stage is a pure function (test in isolation)
- **Easy to debug**: Stack traces point directly to failing stage
- **Easy to extend**: Add new stage = add new function + call in orchestrator
- **Easy to modify**: Change stage logic without affecting others
- **Flexible**: Skip stages conditionally

### Negative

- **More files**: 4 stage modules + 1 orchestrator (vs 1 monolithic file)
  - *Mitigation*: Better organization outweighs file count
- **Orchestrator boilerplate**: Pipeline.run() has some repetition
  - *Mitigation*: ~50 lines, acceptable for clarity

### Neutral

- **No parallelism**: Stages run sequentially (by design)
  - *Rationale*: Stage N+1 depends on output of stage N
  - *Future*: Could parallelize within stages (e.g., probe multiple files concurrently)

## Implementation Guidelines

### For Junior Engineers

When adding a new stage:

1. **Create a new file** in `stages/` directory
2. **Define a pure function** with signature:
   ```python
   def new_stage(inputs, config: PipelineConfig, logger: Logger) -> outputs:
       """Docstring explaining what this stage does."""
       pass
   ```
3. **Add to Pipeline.run()** in correct order
4. **Write tests** for the stage function (test/test_new_stage.py)

### When to Use This Pattern

✅ **Use linear pipeline architecture when**:
- Processing has clear sequential steps
- Each step depends on previous step's output
- You need to test/debug steps independently
- You want to skip certain steps conditionally

❌ **Don't use linear pipeline architecture when**:
- Steps can run in parallel (use async/threads)
- Steps are independent (use separate scripts)
- Order changes frequently (use event-driven)
- Real-time processing (use streaming architecture)

## Examples from Other Projects

This pattern is common in data processing:

### Unix Pipelines

```bash
cat input.txt | grep "error" | sort | uniq -c | sort -nr
#   stage1       stage2       stage3  stage4    stage5
```

Each command is a "stage" that takes input and produces output.

### Apache Beam

```python
(pipeline
 | 'Read' >> ReadFromText('input.txt')
 | 'Parse' >> beam.Map(parse_line)
 | 'Filter' >> beam.Filter(is_valid)
 | 'Transform' >> beam.Map(transform)
 | 'Write' >> WriteToText('output.txt'))
```

Linear stages with explicit data flow.

### ETL Pipelines

```python
# Extract
data = extract_from_database(query)

# Transform
cleaned = clean_data(data)
enriched = enrich_data(cleaned)

# Load
load_to_warehouse(enriched)
```

Three stages, each a pure function.

## Related Decisions

- [ADR 002: Pure Functions for Stages](002-pure-functions.md) - Why stages are functions, not methods
- [ADR 003: Dataclass Configuration](003-dataclass-config.md) - How config flows through stages

## References

- *Functional Core, Imperative Shell* pattern: https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell
- *Pipeline Pattern*: https://martinfowler.com/articles/collection-pipeline/
- *SOLID Principles* (Single Responsibility): https://en.wikipedia.org/wiki/SOLID

## Review History

- **2025-01-15**: Initial decision (approved)

---

**Key Takeaway for Junior Engineers**: When you have sequential processing steps, make each step a **pure function** with explicit inputs/outputs. This makes code easier to understand, test, and debug. The small overhead of an orchestrator is worth the gains in maintainability.
