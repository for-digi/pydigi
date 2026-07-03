"""A tiny name -> model registry so the CLI can pick a model by string.

Kept separate from any concrete model to avoid import cycles.
"""

_REGISTRY = {}


def register(model_class):
    """Register a model under its ``name`` attribute. Usable as a decorator.

    :raises ValueError: if the class has no ``name``, or if a *different* class
        is already registered under that name (re-registering the same class is
        fine, so re-imports don't blow up).
    """
    name = getattr(model_class, "name", None)
    if not name:
        raise ValueError("model %r must define a non-empty 'name'" % (model_class,))
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not model_class:
        raise ValueError(
            "model name %r is already registered to %r" % (name, existing)
        )
    _REGISTRY[name] = model_class
    return model_class


def get_model(name):
    """Return the model class registered under ``name``.

    :raises KeyError: with the list of known models, if ``name`` is unknown.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError("Unknown scale model %r. Known models: %s" % (name, known))


def available_models():
    """Sorted list of registered model names."""
    return sorted(_REGISTRY)
