# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import os
import time
import torch
import logging
import subprocess

__all__ = ["AutoGPU"]

_logger = logging.getLogger(f"sr_harness.{__name__}")


class AutoGPU:
    """Helper that queries ``nvidia-smi`` to select a GPU with sufficient free VRAM."""

    def __init__(self):
        """Initialize the GPU memory monitor and query initial free VRAM across available GPUs."""
        visible_devices = os.getenv("CUDA_VISIBLE_DEVICES")
        if visible_devices:
            self.gpu_list = list(map(int, visible_devices.split(",")))
        else:
            self.gpu_list = [i for i in range(torch.cuda.device_count())]
        self.free_memory = {
            i: self.query_free_memory(j) for i, j in enumerate(self.gpu_list)
        }  # cuda:i -> memory of j-th GPU

    def update_free_memory(self):
        """Query ``nvidia-smi`` and refresh the cached free memory (in MiB) for each GPU."""
        for i, j in enumerate(self.gpu_list):
            self.free_memory[i] = self.query_free_memory(j)

    def choice_gpu(self, memory_MB, interval=600, force=True):
        """Select a GPU with at least ``memory_MB`` MiB of free VRAM, optionally polling until one becomes available.

        Args:
            memory_MB: Required free GPU memory in MiB.
            interval: Polling interval in seconds when waiting for a GPU to free up.
            force: Whether to fall back to CPU or wait when ``nvidia-smi`` is unavailable.

        Returns:
            int: Selected CUDA device index.
        """
        waiting = False
        while True:
            for i, free_memory in self.free_memory.items():
                if free_memory < memory_MB:
                    continue
                try:
                    device = f"cuda:{i}"
                    free_memory1 = self.query_free_memory(self.gpu_list[i])
                    fuck_cuda = torch.zeros(
                        int(memory_MB), 1024, 256, dtype=torch.float32, device=device
                    )
                    free_memory2 = self.query_free_memory(self.gpu_list[i])
                    if waiting:
                        _logger.note(
                            f"SubProcess[{os.getpid()}]: Choose GPU{self.gpu_list[i]} ({device}) with {memory_MB}MB ({free_memory1}MB -> {free_memory2}MB)"
                        )
                    else:
                        _logger.info(
                            f"SubProcess[{os.getpid()}]: Choose GPU{self.gpu_list[i]} ({device}) with {memory_MB}MB ({free_memory1}MB -> {free_memory2}MB)"
                        )
                    del fuck_cuda
                    return device
                except Exception as e:
                    torch.cuda.empty_cache()
                    continue
            else:
                if force:
                    if not waiting:
                        _logger.warning(f"SubProcess[{os.getpid()}]: Waiting GPU...")
                        waiting = True
                    time.sleep(interval)
                    self.update_free_memory()
                else:  # not force
                    _logger.warning(f"SubProcess[{os.getpid()}]: No available GPU!")
                    return "cpu"

    def query_free_memory(self, gpu_id):
        """Return the currently cached free memory (in MiB) for ``gpu_id``.

        Args:
            gpu_id: Zero-based GPU index.

        Returns:
            int: Free memory in MiB.
        """
        try:
            cmd = f"nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i {gpu_id}"
            return int(
                subprocess.check_output(cmd, shell=True).decode().strip().split("\n")[0]
            )
        except Exception as e:
            _logger.warning(f"Query CUDA (GPU{gpu_id}) Memory Failed! {e}")
            return 0
