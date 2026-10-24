# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
class classproperty(object):
    """Descriptor decorator that turns a method taking ``cls`` into a read-only class property."""
    def __init__(self, fget):
        """Wrap ``fget`` as a class-level property descriptor.

        Args:
            fget: Callable accepting the owner class ``cls`` and returning the property value.
        """
        self.fget = fget

    def __get__(self, owner_instance, owner_class):
        # 无论通过实例调用还是类调用，统一将当前的 class 传给底层函数
        return self.fget(owner_class)
