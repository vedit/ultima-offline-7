"""The two inspectable victims in the Trinsic stables."""
import gargoyles
import pose867


def render(s, f):
    if s == 867 and f in (0, 32):
        return pose867.render(f)
    if s == 414 and f in (26, 58):
        return gargoyles.inamo(f)
    raise ValueError((s, f))


def description(s, f):
    if s == 867 and f in (0, 32):
        return pose867.description(f)
    if s == 414 and f in (26, 58):
        return gargoyles.recipe(s, f)
    raise ValueError((s, f))
