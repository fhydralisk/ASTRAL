# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
from __future__ import annotations
from abc import ABCMeta
from typing import Dict, List, Type, TypeVar

T = TypeVar('T', bound='FactoryMixin')

class FactoryMeta(ABCMeta):
    """Metaclass that maintains an isolated subclass registry per base class family."""
    @property
    def all_registered_classes(cls) -> List[Type]:
        """Return all subclasses registered under this factory hierarchy.

        Returns:
            List[Type]: Registered subclass types.
        """
        return list(cls.REGISTRY_DICT.values())
    
    @property
    def all_registered_names(cls) -> List[str]:
        """Return all registered lookup names under this factory hierarchy.

        Returns:
            List[str]: Registered class names.
        """
        return list(cls.REGISTRY_DICT.keys())


class FactoryMixin(metaclass=FactoryMeta):
    """Mixin providing ``@Cls.register(name)`` and ``Cls.create(name, ...)`` factory registration."""

    REGISTRY_DICT: Dict[str, Type] = None  # type: ignore
    """
    Registry of model classes keyed by name.

    Direct subclasses of FactoryMixin get their own registry.
    Grandchildren share the registry with their parent class.
    """

    def __init_subclass__(cls, **kwargs):
        """Automatically called when a subclass is created.

        Only create a new registry for direct subclasses of FactoryMixin.
        Grandchildren will share the same registry with their parent,
        so registering on StatsTool also makes it visible to BaseTool.
        """
        super().__init_subclass__(**kwargs)
        # Check if FactoryMixin is a direct parent (not just ancestor)
        if FactoryMixin in cls.__bases__:
            cls.REGISTRY_DICT = {}
        # else: inherit REGISTRY_DICT from parent (already via normal inheritance)

    @classmethod
    def register(cls, name: str):
        """Class decorator that registers a subclass under ``name`` (case-insensitive).

        Args:
            name: Unique registry key for the decorated subclass.

        Returns:
            Callable: Decorator that registers and returns the subclass.
        """
        def decorator(model_cls: type) -> type:
            cls.REGISTRY_DICT[name] = model_cls
            model_cls.model_name = name
            return model_cls
        return decorator

    @classmethod
    def create(cls: Type[T], name: str, *args, create_instance=True, **kwargs) -> T | Type[T]:
        """Look up a registered subclass by ``name`` and optionally instantiate it.

        Args:
            name: Registered name of the subclass.
            *args: Positional arguments passed to the subclass constructor when ``create_instance=True``.
            create_instance: If ``True``, instantiate and return the object; if ``False``, return the class itself.
            **kwargs: Keyword arguments passed to the subclass constructor.

        Returns:
            T | Type[T]: Instantiated object or registered subclass.
        """
        # 'default' refers to the base class itself
        if name == 'default':
            model_class = cls
        elif name in cls.REGISTRY_DICT:
            model_class = cls.REGISTRY_DICT[name]
        else:
            available = ['default'] + list(cls.REGISTRY_DICT.keys())
            raise ValueError(
                f"Unknown model type: '{name}'. "
                f"Available models: {available}. "
                f"Make sure the model class is imported (registration happens at import time)."
            )

        return model_class(*args, **kwargs) if create_instance else model_class
