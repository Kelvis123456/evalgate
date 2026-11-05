class EvalGateError(Exception):
    """A problem with user-supplied input (eval set, baseline, app spec).

    The CLI turns these into exit code 2, so they never look like a regression.
    """
