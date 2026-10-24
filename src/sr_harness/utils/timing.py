# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
"""
Lightweight timing utilities for optional performance diagnostics.
"""

import enum
import time
import numpy as np
import pandas as pd
from typing import Literal

__all__ = ["Timer", "NamedTimer", "ParallelTimer"]



Mode = Literal["time", "count", "pace", "speed"]


def humanize_time(time):
    """Format a duration in seconds with human-readable units (``ns``, ``μs``, ``ms``, ``s``, ``min``, ``h``, ``d``).

    Args:
        time: Duration in seconds.

    Returns:
        str: Human-readable duration string.
    """
    if time == 0: return "0 s"
    unit_scale = pd.Series({ # 需要保证从小到大排列
        'μs': 1e-6, 'ms': 1e-3, 's': 1e0, 'min': 60, 'h': 3600, 'day': 86400
    })
    idx = max(0, unit_scale.searchsorted(time, side='right')-1)
    time_unit, scale = unit_scale.index[idx], unit_scale.iloc[idx]
    return f"{time / scale:.3g} {time_unit}"


def humanize_count(count, unit="iter"):
    """Format a numeric count with SI prefixes (``k``, ``M``, ``G``, ``T``) and unit label.

    Args:
        count: Numeric count value.
        unit: Unit suffix appended to the formatted number.

    Returns:
        str: Formatted count string.
    """
    if count == 0: return f"0 {unit}"
    unit_scale = pd.Series({ # 需要保证从小到大排列
        f'n{unit}': 1e-9, f'μ{unit}': 1e-6, f'm{unit}': 1e-3, 
        f'{unit}': 1, f'k{unit}': 1e3, f'M{unit}': 1e6, f'G{unit}': 1e9
    })
    idx = max(0, unit_scale.searchsorted(count, side='right')-1)
    count_unit, scale = unit_scale.index[idx], unit_scale.iloc[idx]
    return f"{count / scale:.3g} {count_unit}"


def humanize_pace(pace, unit="iter"):
    """Format an average pace (seconds per unit) with human-readable time units.

    Args:
        pace: Duration in seconds per unit.
        unit: Unit denominator label (e.g., ``"iter"``).

    Returns:
        str: Formatted pace string such as ``"12.3 ms/iter"``.
    """
    if pace == 0: return f"0 s/{unit}"
    unit_scale = pd.Series({ # 需要保证从小到大排列
        f'μs/{unit}': 1e-6, f'ms/{unit}': 1e-3, f's/{unit}': 1e0, 
        f'min/{unit}': 60, f'h/{unit}': 3600, f'day/{unit}': 86400
    })
    idx = max(0, unit_scale.searchsorted(pace, side='right')-1)
    pace_unit, scale = unit_scale.index[idx], unit_scale.iloc[idx]
    return f"{pace / scale:.3g} {pace_unit}"


def humanize_speed(speed, unit="iter"):
    """Format a throughput rate (units per second) with SI prefixes.

    Args:
        speed: Rate in units per second.
        unit: Unit numerator label (e.g., ``"iter"``).

    Returns:
        str: Formatted speed string such as ``"81.3 iter/s"``.
    """
    if speed == 0: return f"0 {unit}/s"
    unit_scale = pd.Series({ # 需要保证从小到大排列
        f'{unit}/day': 1/86400, f'{unit}/h': 1/3600, f'{unit}/min': 1/60, f'{unit}/s': 1,
        f'k{unit}/s': 1e3, f'M{unit}/s': 1e6, f'G{unit}/s': 1e9
    })
    idx = max(0, unit_scale.searchsorted(speed, side='right')-1)
    speed_unit, scale = unit_scale.index[idx], unit_scale.iloc[idx]
    return f"{speed / scale:.3g} {speed_unit}"


class Timer:
    """Accumulator that tracks elapsed wall-clock time and iteration counts to report pace or throughput."""
    def __init__(self, unit="iter"):
        """Initialize the timer with zero elapsed time and zero count.

        Args:
            unit: Name of the counted item (defaults to ``"iter"``).
        """
        self._count = 0
        self._time = 0
        self.unit = unit
        self.last_add_time = time.time()

    def add(self, n=1, by: Literal["increment", "absolute"]="increment"):
        """Record elapsed time since the previous ``add`` call and update the item counter.

        Args:
            n: Count increment (when ``by="increment"``) or new total count (when ``by="absolute"``).
            by: Whether ``n`` is an incremental delta (``"increment"``) or an absolute total (``"absolute"``).
        """
        if by == "increment": self._count += n
        elif by == "absolute": self._count = n
        self._time += (now := time.time()) - self.last_add_time
        self.last_add_time = now

    def clear(self, reset_last_add_time=False):
        """Reset accumulated time and count to zero.

        Args:
            reset_last_add_time: If ``True``, also reset the reference timestamp to ``time.time()``.
        """
        self._count = 0
        self._time = 0
        if reset_last_add_time:
            self.last_add_time = time.time()
    
    def to_str(self, mode: Mode = 'pace'):
        """Format the accumulated time and count/pace/speed as a human-readable string.

        Args:
            mode: Metric to display alongside total time (``"pace"``, ``"speed"``, ``"count"``, or ``None``).

        Returns:
            str: Formatted timing summary.
        """
        if mode == 'pace': return humanize_pace(self.pace, unit=self.unit)
        elif mode == "speed": return humanize_speed(self.speed, unit=self.unit)
        elif mode == "count": return humanize_count(self.count, unit=self.unit)
        elif mode == "time": return humanize_time(self.time)
        else: raise ValueError(f"Unknown mode: {mode}. Supported modes are 'pace', 'speed', 'count', and 'time'.")

    def __str__(self):
        time = self.time_str()
        count = self.count_str()
        pace = self.pace_str()
        speed = self.speed_str()
        return f"{type(self).__name__}(time={time}, count={count}, pace={pace}, speed={speed})"

    def __repr__(self):
        return self.__str__()
    
    @property
    def time(self):
        """Return total accumulated time in seconds."""
        return self._time
    @property
    def count(self):
        """Return total accumulated item count."""
        return self._count
    @property
    def pace(self):
        """Return average seconds per item (``time / count``)."""
        return self.time / self.count if self.count != 0 else 0
    @property
    def speed(self):
        """Return average items per second (``count / time``)."""
        return self.count / self.time if self.time != 0 else 0
    def time_str(self):
        """Return total accumulated time formatted with human-readable units."""
        return humanize_time(self.time)
    def count_str(self):
        """Return total accumulated count formatted with SI prefixes."""
        return humanize_count(self.count, unit=self.unit)
    def pace_str(self):
        """Return average pace formatted with human-readable time units per item."""
        return humanize_pace(self.pace, unit=self.unit)
    def speed_str(self):
        """Return average throughput formatted with SI prefixes per second."""
        return humanize_speed(self.speed, unit=self.unit)

    def to_dict(self):
        """Serialize the timer state to a dictionary.

        Returns:
            dict[str, Any]: Dictionary containing ``unit``, ``time``, and ``count``.
        """
        return {
            '_count': self._count,
            '_time': self._time,
            'unit': self.unit,
        }

    @classmethod
    def from_dict(cls, dict):
        """Restore a :class:`Timer` instance from a dictionary produced by :meth:`to_dict`.

        Args:
            dict: Serialized timer dictionary.

        Returns:
            Timer: Reconstructed timer instance.
        """
        timer = cls(unit=dict['unit'])
        timer._count = dict['_count']
        timer._time = dict['_time']
        return timer


class NamedTimer(Timer):
    """Multi-category timer that attributes elapsed time and counts to named sub-operations."""
    def __init__(self, unit="iter"):
        """Initialize the named timer with empty per-category counters.

        Args:
            unit: Name of the counted item (defaults to ``"iter"``).
        """
        super().__init__(unit=unit)
        self._count = {}
        self._time = {}

    def add(self, name, n=1, by: Literal["increment", "absolute"]="increment"):
        """Record elapsed time and count under category ``name``.

        Args:
            name: Sub-operation category label.
            n: Count increment or absolute count value.
            by: Whether ``n`` is an ``"increment"`` or ``"absolute"`` count.
        """
        if name and name not in self.names:
            self._time[name] = self._count[name] = 0
        if name is None: pass
        elif by == "increment": self._count[name] += n
        elif by == "absolute": self._count[name] = n
        self._time[name] += (now := time.time()) - self.last_add_time
        self.last_add_time = now

    def clear(self, reset_last_add_time=False):
        """Reset all recorded category times and counts.

        Args:
            reset_last_add_time: If ``True``, reset the reference timestamp to ``time.time()``.
        """
        self._count = {}
        self._time = {}
        if reset_last_add_time:
            self.last_add_time = time.time()

    def to_str(
            self, 
            mode: Mode='pace', 
            mode_of_detail: Mode|None='pace', 
            mode_of_percent: Literal['by_time', 'by_count']|None='by_time',
        ):
        """Format total time and a breakdown of per-category times/percentages sorted by share.

        Args:
            mode: Summary mode for the total timer (``"pace"``, ``"speed"``, ``"count"``, or ``None``).
            mode_of_detail: Summary mode for each category entry.
            mode_of_percent: Whether category percentages are computed ``"by_time"`` or ``"by_count"``.

        Returns:
            str: Formatted timing breakdown string.
        """
        if mode == "time": total = humanize_time(self.time)
        elif mode == "count": total = humanize_count(self.count, unit=self.unit)
        elif mode == "pace": total = humanize_pace(self.pace, unit=self.unit)
        elif mode == "speed": total = humanize_speed(self.speed, unit=self.unit)
        else: raise ValueError(f"Unknown mode: {mode}. Supported modes are 'pace', 'speed', 'count', and 'time'.")

        if mode_of_detail is None: detail = {k: "" for k in self.names}
        elif mode_of_detail == "time": detail = {k: humanize_time(self.get_named_time(k)) for k in self.names}
        elif mode_of_detail == "count": detail = {k: humanize_count(self.get_named_count(k), unit=self.unit) for k in self.names}
        elif mode_of_detail == "pace": detail = {k: humanize_pace(self.get_named_pace(k), unit=self.unit) for k in self.names}
        elif mode_of_detail == "speed": detail = {k: humanize_speed(self.get_named_speed(k), unit=self.unit) for k in self.names}
        else: raise ValueError(f"Unknown mode_of_detail: {mode_of_detail}. Supported modes are 'pace', 'speed', 'count', and 'time'.")

        if mode_of_percent is None: percent = {k: 0 for k in self.names}
        elif mode_of_percent == 'by_time': percent = {k: self.get_named_time(k) / self.time if self.time > 0 else 0 for k in self.names}
        elif mode_of_percent == 'by_count': percent = {k: self.get_named_count(k) / self.count if self.count > 0 else 0 for k in self.names}
        else: raise ValueError(f"Unknown mode: {mode_of_percent}. Supported modes are 'by_time' and 'by_count'.")
        
        detail_str = []
        for k in sorted(self.names, key=percent.get, reverse=True):
            if detail[k] and percent[k]:
                detail_str.append(f"{k}={detail[k]}[{percent[k]:.0%}]")
            elif detail[k]:
                detail_str.append(f"{k}={detail[k]}")
            elif percent[k]:
                detail_str.append(f"{k}[{percent[k]:.0%}]")
            else:
                pass
        detail_str = f" ({'; '.join(detail_str)})" if detail_str else ""
        return f'{total}{detail_str}'

    @property
    def names(self):
        """Return the list of recorded category names."""
        return list(self._time.keys())
    @property
    def time(self):
        """Return total elapsed time summed across all categories."""
        return sum(self._time.values())
    @property
    def count(self):
        """Return total count summed across all categories."""
        return sum(self._count.values())
    def get_named_time(self, name):
        """Return elapsed seconds recorded for category ``name``.

        Args:
            name: Category name to query.

        Returns:
            float: Accumulated time in seconds for ``name``.
        """
        return self._time[name]
    def get_named_count(self, name):
        """Return the accumulated item count for category ``name``.

        Args:
            name: Category name to query.

        Returns:
            float: Accumulated count for ``name``.
        """
        return self._count[name]
    def get_named_pace(self, name):
        """Return average seconds per item for category ``name``.

        Args:
            name: Category name to query.

        Returns:
            float: Pace in seconds per item for ``name``.
        """
        return self._time[name] / self._count[name] if self._count[name] != 0 else 0
    def get_named_speed(self, name):
        """Return average items per second for category ``name``.

        Args:
            name: Category name to query.

        Returns:
            float: Throughput in items per second for ``name``.
        """
        return self._count[name] / self._time[name] if self._time[name] != 0 else 0
    @property
    def named_time(self):
        """Return a dictionary mapping each category name to its accumulated seconds."""
        return {k: self.get_named_time(k) for k in self.names}
    @property
    def named_count(self):
        """Return a dictionary mapping each category name to its accumulated count."""
        return {k: self.get_named_count(k) for k in self.names}
    @property
    def named_pace(self):
        """Return a dictionary mapping each category name to its average pace."""
        return {k: self.get_named_pace(k) for k in self.names}
    @property
    def named_speed(self):
        """Return a dictionary mapping each category name to its average throughput."""
        return {k: self.get_named_speed(k) for k in self.names}


class ParallelTimer(Timer):
    """Timer that tracks separate counts per named category against a single shared wall-clock duration."""
    def __init__(self, unit="iter"):
        """Initialize the parallel counter timer.

        Args:
            unit: Name of the counted item (defaults to ``"iter"``).
        """
        super().__init__(unit=unit)
        self._count = {}

    def add(self, name, n=1, by: Literal["increment", "absolute"]="increment"):
        """Update the shared wall-clock time and record ``n`` items under category ``name``.

        Args:
            name: Category label.
            n: Count increment or absolute count value.
            by: Whether ``n`` is an ``"increment"`` or ``"absolute"`` count.
        """
        if name and name not in self.names:
            self._count[name] = 0
        if name is None: pass
        elif by == "increment": self._count[name] += n
        elif by == "absolute": self._count[name] = n
        self._time += (now := time.time()) - self.last_add_time
        self.last_add_time = now

    def clear(self, reset_last_add_time=False):
        """Reset shared elapsed time and all per-category counts.

        Args:
            reset_last_add_time: If ``True``, reset the reference timestamp to ``time.time()``.
        """
        self._count = {}
        self._time = 0
        if reset_last_add_time:
            self.last_add_time = time.time()

    def to_str(
            self, 
            mode: Mode='pace', 
            mode_of_detail: Mode|None='pace', 
            mode_of_percent: Literal['by_time', 'by_count']|None='by_time'
        ):
        """Format total count/rate and a per-category breakdown.

        Args:
            mode: Summary mode for the overall total.
            mode_of_detail: Summary mode for each category entry.
            mode_of_percent: Whether percentages are computed ``"by_time"`` or ``"by_count"``.

        Returns:
            str: Formatted breakdown string.
        """
        if mode == "time": total = humanize_time(self.time)
        elif mode == "count": total = humanize_count(self.count, unit=self.unit)
        elif mode == "pace": total = humanize_pace(self.pace, unit=self.unit)
        elif mode == "speed": total = humanize_speed(self.speed, unit=self.unit)
        else: raise ValueError(f"Unknown mode: {mode}. Supported modes are 'pace', 'speed', 'count', and 'time'.")

        if mode_of_detail is None: detail = {k: "" for k in self.names}
        elif mode_of_detail == "time": detail = {k: humanize_time(self.get_named_time(k)) for k in self.names} # 不建议，因为 time 是共享的
        elif mode_of_detail == "count": detail = {k: humanize_count(self.get_named_count(k), unit=self.unit) for k in self.names}
        elif mode_of_detail == "pace": detail = {k: humanize_pace(self.get_named_pace(k), unit=self.unit) for k in self.names}
        elif mode_of_detail == "speed": detail = {k: humanize_speed(self.get_named_speed(k), unit=self.unit) for k in self.names}
        else: raise ValueError(f"Unknown mode_of_detail: {mode_of_detail}. Supported modes are 'pace', 'speed', 'count', and 'time'.")

        if mode_of_percent is None: percent = {k: None for k in self.names}
        elif mode_of_percent == 'by_time': percent = {k: self.get_named_time(k) / self.time if self.time > 0 else None for k in self.names} # 不建议，因为 time 是共享的
        elif mode_of_percent == 'by_count': percent = {k: self.get_named_count(k) / self.count if self.count > 0 else None for k in self.names}
        else: raise ValueError(f"Unknown mode: {mode_of_percent}. Supported modes are 'by_time' and 'by_count'.")
        
        detail_str = []
        for k in sorted(self.names, key=lambda x: percent.get(x) or -float('inf'), reverse=True):
            if detail[k] and percent[k]:
                detail_str.append(f"{k}={detail[k]}[{percent[k]:.0%}]")
            elif detail[k]:
                detail_str.append(f"{k}={detail[k]}")
            elif percent[k]:
                detail_str.append(f"{k}[{percent[k]:.0%}]")
            else:
                pass
        detail_str = f" ({'; '.join(detail_str)})" if detail_str else ""
        return f'{total}{detail_str}'

    @property
    def names(self):
        """Return the list of recorded category names."""
        return list(self._count.keys())
    @property
    def count(self):
        """Return the total count summed across all categories."""
        return sum(self._count.values())
    def get_named_time(self, name):
        """Return the shared elapsed wall-clock time for category ``name``.

        Args:
            name: Category name to query.

        Returns:
            float: Shared elapsed time in seconds.
        """
        return self._time
    def get_named_count(self, name):
        """Return the accumulated count for category ``name``.

        Args:
            name: Category name to query.

        Returns:
            float: Count recorded for ``name``.
        """
        return self._count[name]
    def get_named_pace(self, name):
        """Return shared elapsed time divided by the count for category ``name``.

        Args:
            name: Category name to query.

        Returns:
            float: Effective pace for ``name``.
        """
        return self._time / self._count[name] if self._count[name] != 0 else 0
    def get_named_speed(self, name):
        """Return the count for category ``name`` divided by shared elapsed time.

        Args:
            name: Category name to query.

        Returns:
            float: Effective throughput for ``name``.
        """
        return self._count[name] / self._time if self._time != 0 else 0
    @property
    def named_time(self):
        """Return a dictionary mapping each category name to the shared elapsed time."""
        return {k: self.get_named_time(k) for k in self.names}
    @property
    def named_count(self):
        """Return a dictionary mapping each category name to its count."""
        return {k: self.get_named_count(k) for k in self.names}
    @property
    def named_pace(self):
        """Return a dictionary mapping each category name to its effective pace."""
        return {k: self.get_named_pace(k) for k in self.names}
    @property
    def named_speed(self):
        """Return a dictionary mapping each category name to its effective throughput."""
        return {k: self.get_named_speed(k) for k in self.names}
