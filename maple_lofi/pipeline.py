"""Main pipeline orchestration."""

import logging
import time
from pathlib import Path

from maple_lofi.config import PipelineConfig
from maple_lofi.ffmpeg.executor import ProcessingError
from maple_lofi.logging.logger import setup_logger
from maple_lofi.logging.manifest import ManifestBuilder
from maple_lofi.stages.ingest import ingest_stage
from maple_lofi.stages.lofi import lofi_stage
from maple_lofi.stages.merge import merge_stage
from maple_lofi.stages.video import video_stage
from maple_lofi.utils.validators import ValidationError


class OutputError(Exception):
    """Raised when output operations fail (exit code 3)."""
    pass


class Pipeline:
    """Orchestrates all 4 pipeline stages."""

    def __init__(self, config: PipelineConfig):
        """Initialize pipeline.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.logger = setup_logger(config.output_dir / "run_log.txt")
        self.manifest = ManifestBuilder(config)

    def run(self) -> int:
        """Run the complete pipeline.

        Returns:
            Exit code (0=success, 1=validation error, 2=processing error, 3=output error)
        """
        self.logger.info("=" * 60)
        self.logger.info("Maple Lofi Pipeline")
        self.logger.info("=" * 60)
        self.logger.info(f"Run ID: {self.config.run_id}")
        self.logger.info(f"Timestamp: {self.config.timestamp}")
        self.logger.info("")

        try:
            # Stage 1: Ingest
            start_time = time.time()
            tracks = ingest_stage(self.config, self.logger)
            ingest_duration = time.time() - start_time

            # Add to manifest
            self.manifest.add_input_tracks(
                tracks,
                order_source="order.txt" if (self.config.input_dir / "order.txt").exists() else "natural_sort"
            )
            self.manifest.add_input_asset("cover_image", self.config.cover_image)
            self.manifest.add_input_asset("texture", self.config.texture)
            self.manifest.add_input_asset("drums", self.config.drums)
            self.manifest.add_stage_result(
                "ingest",
                "success",
                ingest_duration,
                tracks_found=len(tracks)
            )

            self.logger.info("")

            # Stage 2: Merge
            start_time = time.time()
            merged_clean = merge_stage(tracks, self.config, self.logger)
            merge_duration = time.time() - start_time

            self.manifest.add_output("merged_clean", merged_clean)
            self.manifest.add_stage_result(
                "merge",
                "success",
                merge_duration,
                crossfades_applied=len(tracks) - 1
            )

            self.logger.info("")

            # Stage 3: Lofi (optional)
            if not self.config.skip_lofi:
                start_time = time.time()
                merged_lofi = lofi_stage(merged_clean, self.config, self.logger)
                lofi_duration = time.time() - start_time

                self.manifest.add_output("merged_lofi_wav", merged_lofi)
                self.manifest.add_output("merged_lofi_mp3", self.config.output_dir / "merged_lofi.mp3")
                self.manifest.add_stage_result(
                    "lofi",
                    "success",
                    lofi_duration
                )

                final_audio = merged_lofi
            else:
                self.logger.info("=== Stage 3: Lofi Transformation ===")
                self.logger.info("Skipping lofi stage (--skip-lofi)")
                self.manifest.add_stage_result(
                    "lofi",
                    "skipped",
                    0.0
                )
                final_audio = merged_clean

            self.logger.info("")

            # Stage 4: Video (optional)
            if self.config.cover_image:
                start_time = time.time()
                final_video = video_stage(final_audio, self.config, self.logger)
                video_duration = time.time() - start_time

                if final_video:
                    self.manifest.add_output("final_video", final_video)
                    thumbnail_ext = self.config.cover_image.suffix
                    thumbnail_path = self.config.output_dir / f"thumbnail{thumbnail_ext}"
                    self.manifest.add_output("thumbnail", thumbnail_path)

                self.manifest.add_stage_result(
                    "video",
                    "success",
                    video_duration
                )
            else:
                self.logger.info("=== Stage 4: Video Rendering ===")
                self.logger.info("No cover image specified, skipping video rendering")
                self.manifest.add_stage_result(
                    "video",
                    "skipped",
                    0.0
                )

            self.logger.info("")

            # Write manifest
            manifest_path = self.config.output_dir / "manifest.json"
            self.manifest.write(manifest_path)
            self.logger.info(f"Manifest written to {manifest_path}")

            # Success summary
            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info("Pipeline completed successfully!")
            self.logger.info("=" * 60)
            self.logger.info(f"Output directory: {self.config.output_dir}")
            self.logger.info("")
            self.logger.info("Outputs:")
            for name, data in self.manifest.data["outputs"].items():
                path = Path(data["path"])
                self.logger.info(f"  ✓ {path.name} ({data['file_size_mb']}MB)")

            return 0

        except ValidationError as e:
            self.logger.error(f"Validation error: {e}")
            self.manifest.add_error(str(e))
            self._write_manifest_on_error()
            return 1

        except ProcessingError as e:
            self.logger.error(f"Processing error: {e}")
            self.manifest.add_error(str(e))
            self._write_manifest_on_error()
            return 2

        except OutputError as e:
            self.logger.error(f"Output error: {e}")
            self.manifest.add_error(str(e))
            self._write_manifest_on_error()
            return 3

        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self.manifest.add_error(f"Unexpected error: {e}")
            self._write_manifest_on_error()
            import traceback
            traceback.print_exc()
            return 2

    def _write_manifest_on_error(self):
        """Write manifest even on error (for debugging)."""
        try:
            manifest_path = self.config.output_dir / "manifest.json"
            self.manifest.write(manifest_path)
            self.logger.info(f"Partial manifest written to {manifest_path}")
        except Exception as e:
            self.logger.error(f"Failed to write manifest: {e}")
