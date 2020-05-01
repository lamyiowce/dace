import dace
from dace.sdfg import SDFG, SDFGState


class NestedCall():
    """An object to support nested calls in replacement functions. It does this by keeping track of
       the last added state.

       Example usage:
       def _cos_then_max(sdfg, state, a: str):
           nest = NestedCall(sdfg, state)

           # you don't need to pass the first two args
           c = nest(_cos)(a)
           result = nest(_max)(a, axis=1)

           # return a tuple of the nest object and the result
           return nest, result
    """
    def __init__(self, sdfg: SDFG, state: SDFGState):
        self.sdfg = sdfg
        self.state = state
        self.last_state = state
        self.count = 0

    def __call__(self, func):
        def nested(*args, **kwargs):
            result = func(self.sdfg, self.add_state(func.__name__), *args,
                          **kwargs)
            if isinstance(result, tuple) and type(result[0]) is NestedCall:
                self.last_state = result[0].last_state
                result = result[1]
            return result

        return nested

    def add_state(self, func_name):
        self.count += 1
        state = self.sdfg.add_state("{}_nested_call_{}_{}".format(
            self.state.label, self.count, func_name))
        self.sdfg.add_edge(self.last_state, state, dace.InterstateEdge())
        self.last_state = state
        return state