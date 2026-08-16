"""`jdk.internal.math.FloatingDecimal`, the binary-to-decimal half, ported.

Split out of `javafmt.py` only because the two together are over the file-size
limit, and this is the seam that leaves both halves coherent: everything here is
a transcription of one Java class and answers one question, "which decimal
digits does the JVM pick for these bits". `javafmt.py` is where those digits
become the bytes of an occurrence. Nothing outside `javafmt.py` should import
this; a rule wants `float32_str`, `double_str` or `fmt2`.

**JDK 17, deliberately.** `Float.toString` and `Double.toString` were rewritten
in JDK 19 (JDK-4511638) to emit the shortest decimal that round-trips. This is
the older algorithm, which sometimes emits one digit more: over two million
random bit patterns it prints a non-shortest string for about 11% of floats.
Upstream's pom targets 17, so 17 is what compat has to reproduce, and no
shortest-repr shortcut can stand in for it.
"""

from __future__ import annotations

import math
import struct

EXP_SHIFT = 52
FRACT_HOB = 1 << EXP_SHIFT
SIGNIF_MASK = FRACT_HOB - 1
_EXP_ONE = 1023 << EXP_SHIFT
_MAX_SMALL_BIN_EXP = 62
_MIN_SMALL_BIN_EXP = -(63 // 3)


def float_digits(bits: int, *, compatible: bool) -> tuple[bool, str | None, int]:
    """`getBinaryToASCIIConverter(float)`, from the raw 32 bits.

    Returns `(negative, digits, dec_exp)`, where the value is
    `0.<digits> * 10 ** dec_exp` and `digits` is `None` for a NaN or infinity.
    """
    negative = bool(bits >> 31)
    fract = bits & 0x7FFFFF
    bin_exp = (bits >> 23) & 0xFF
    if bin_exp == 0xFF:
        return negative, None, 0
    if bin_exp == 0:
        if fract == 0:
            return negative, "0", 0
        # Normalise the subnormal the way FloatingDecimal does: shift the
        # leading one up into the hidden-bit position, pay for it in the
        # exponent, and keep the reduced significant-bit count.
        leading_zeros = 32 - fract.bit_length()
        shift = leading_zeros - 8
        fract <<= shift
        bin_exp = 1 - shift
        n_significant = 32 - leading_zeros
    else:
        fract |= 1 << 23
        n_significant = 24
    return negative, *dtoa(bin_exp - 127, fract << 29, n_significant, compatible=compatible)


def double_digits(bits: int, *, compatible: bool) -> tuple[bool, str | None, int]:
    """`getBinaryToASCIIConverter(double)`, from the raw 64 bits."""
    negative = bool(bits >> 63)
    fract = bits & SIGNIF_MASK
    bin_exp = (bits >> EXP_SHIFT) & 0x7FF
    if bin_exp == 0x7FF:
        return negative, None, 0
    if bin_exp == 0:
        if fract == 0:
            return negative, "0", 0
        leading_zeros = 64 - fract.bit_length()
        shift = leading_zeros - (63 - EXP_SHIFT)
        fract <<= shift
        bin_exp = 1 - shift
        n_significant = 64 - leading_zeros
    else:
        fract |= FRACT_HOB
        n_significant = EXP_SHIFT + 1
    return negative, *dtoa(bin_exp - 1023, fract, n_significant, compatible=compatible)


def dtoa(
    bin_exp: int, fract_bits: int, n_significant_bits: int, *, compatible: bool
) -> tuple[str, int]:
    """`BinaryToASCIIBuffer.dtoa`: the digits, and where the decimal point goes.

    Java has three arithmetic paths through the second half (int, long and
    `FDBigInteger`) that differ only in overflow behaviour. Python's ints are
    unbounded, so this is the `FDBigInteger` path, the one with no overflow hack
    in it. `tools/diff_javafmt_against_java.py` is what says the other two never
    diverge from it on a real corpus, rather than an argument that they cannot.
    """
    tail_zeros = (fract_bits & -fract_bits).bit_length() - 1
    n_fract_bits = EXP_SHIFT + 1 - tail_zeros
    n_tiny_bits = max(0, n_fract_bits - bin_exp - 1)
    if n_tiny_bits == 0 and _MIN_SMALL_BIN_EXP <= bin_exp <= _MAX_SMALL_BIN_EXP:
        # The integral fast path, and the reason JDK 17 is not always shortest:
        # it drops whole decimal digits it deems insignificant and rounds what
        # is left, which can leave a digit the shortest form does not need.
        insignificant = (
            _insignificant_digits_for_pow2(bin_exp - n_significant_bits - 1)
            if bin_exp > n_significant_bits
            else 0
        )
        if bin_exp >= EXP_SHIFT:
            scaled = fract_bits << (bin_exp - EXP_SHIFT)
        else:
            scaled = fract_bits >> (EXP_SHIFT - bin_exp)
        return _develop_long_digits(scaled, insignificant)

    dec_exp = _estimate_dec_exp(fract_bits, bin_exp)
    b5 = max(0, -dec_exp)
    b2 = b5 + n_tiny_bits + bin_exp
    s5 = max(0, dec_exp)
    s2 = s5 + n_tiny_bits
    m5, m2 = b5, b2 - n_significant_bits
    fract_bits >>= tail_zeros
    b2 -= n_fract_bits - 1
    common = min(b2, s2)
    b2 -= common
    s2 -= common
    m2 -= common
    if n_fract_bits == 1:
        # Below an exact power of two the next float is only half as far away,
        # so Java hacks the half-ulp down. Its own comment is "Hope this works."
        m2 -= 1
    if m2 < 0:
        b2 -= m2
        s2 -= m2
        m2 = 0
    b_bits = n_fract_bits + b2 + _n5bits(b5)
    ten_s_bits = s2 + 1 + _n5bits(s5 + 1)
    if b_bits < 32 and ten_s_bits < 32:
        width: int | None = 32
    elif b_bits < 64 and ten_s_bits < 64:
        width = 64
    else:
        width = None
    return _generate(
        (fract_bits * 5**b5) << b2,
        5**s5 << s2,
        5**m5 << m2,
        dec_exp,
        compatible=compatible,
        width=width,
    )


def _generate(
    b: int, s: int, m: int, dec_exp: int, *, compatible: bool, width: int | None
) -> tuple[str, int]:
    """Divide out the digits until the remainder is inside half an ulp.

    `width` is which of Java's three arithmetic branches this is, chosen by the
    same `Bbits`/`tenSbits` estimate: 32 for the int branch, 64 for the long
    one, `None` for `FDBigInteger`. It is not a performance detail, and dropping
    it costs output bytes. Two ways:

    - the int and long branches ask `b + m > tens` in fixed-width arithmetic,
      and that sum overflows. `tools/diff_javafmt_against_java.py` found twelve
      floats near 1e25 (0x6a6425e2 among them) where the long branch wraps to a
      negative sum, reads `high` as false, and stops one rounding step short of
      what unbounded arithmetic would do;
    - the `FDBigInteger` branch asks `tenSval.addAndCmp(Bval, Mval) <= 0`, which
      is `b + m >= tens`. The JDK's three branches genuinely disagree on the
      equality boundary, so this one is `>=` and the other two are `>`.
    """
    tens = _wrap(s * 10, width)
    digits: list[int] = []
    q, b = _step(b, s, width)
    m = _wrap(m * 10, width)
    low, high = b < m, _above(b, m, tens, width)
    if q == 0 and not high:
        dec_exp -= 1
    else:
        digits.append(q)
    if not compatible or dec_exp < -3 or dec_exp >= 8:
        # Java writes at least one digit after the point, so E-form needs a
        # second digit. `%f` passes compatible=False and always gets one.
        low = high = False
    while not low and not high:
        q, b = _step(b, s, width)
        m = _wrap(m * 10, width)
        if width is not None and m <= 0:
            # Java: "hack -- m might overflow! in this case, it is certainly
            # > b, which won't". It stops rather than trust the wrapped value.
            low = high = True
        else:
            low, high = b < m, _above(b, m, tens, width)
        digits.append(q)
    low_digit_difference = _wrap((b << 1) - tens, width)
    dec_exp += 1
    if high and (
        not low or low_digit_difference > 0 or (low_digit_difference == 0 and digits[-1] & 1)
    ):
        dec_exp += _roundup(digits)
    return "".join(map(str, digits)), dec_exp


def _step(b: int, s: int, width: int | None) -> tuple[int, int]:
    """`q = b / s; b = 10 * (b % s)`. Both stay non-negative and in range.

    The `Bbits`/`tenSbits` guards are what promise that: `b % s < s` and
    `10 * s` is `tens`, which the branch was chosen to fit. Only the sums below
    overflow, which is why the wrap is there and not here.
    """
    q, remainder = divmod(b, s)
    return q, _wrap(10 * remainder, width)


def _above(b: int, m: int, tens: int, width: int | None) -> bool:
    if width is None:
        return b + m >= tens
    return _wrap(b + m, width) > tens


def _wrap(value: int, width: int | None) -> int:
    """Java's two's-complement `int` and `long`, or Python's unbounded ints."""
    if width is None:
        return value
    value &= (1 << width) - 1
    return value - (1 << width) if value >> (width - 1) else value


def _n5bits(index: int) -> int:
    """`N_5_BITS`, which is `ceil(log2(5**i))` up to 26 and `3 * i` past it."""
    if index == 0:
        return 0
    if index < 27:
        return (5**index).bit_length()
    return index * 3


def _develop_long_digits(value: int, insignificant: int) -> tuple[str, int]:
    """`developLongDigits`: drop insignificant digits, then trailing zeros.

    Java peels digits off the low end, counting each into the exponent, which
    comes to the same thing as stripping the trailing zeros and taking the
    length of the whole decimal string.
    """
    dec_exp = 0
    if insignificant != 0:
        pow10 = 10**insignificant
        residue = value % pow10
        value //= pow10
        dec_exp += insignificant
        if residue >= pow10 >> 1:
            value += 1
    text = str(value)
    return text.rstrip("0"), dec_exp + len(text)


def _insignificant_digits_for_pow2(p2: int) -> int:
    """`insignificantDigitsForPow2`, computed rather than transcribed.

    Its table is `floor(log10(2**p2))` for `1 < p2 < 64` and zero outside, which
    is exactly what the comment above it in FloatingDecimal.java says it is.
    """
    if 1 < p2 < 64:
        return len(str(1 << p2)) - 1
    return 0


def _estimate_dec_exp(fract_bits: int, bin_exp: int) -> int:
    """`estimateDecExp`, whose bit-twiddled tail is a floor of the same double.

    Every operation is IEEE double in the order Java writes it, so the estimate
    is reproducible rather than approximate. It only has to be within one of the
    true exponent; the unrolled first `dtoa` iteration corrects it.
    """
    d2 = struct.unpack("<d", struct.pack("<Q", _EXP_ONE | (fract_bits & SIGNIF_MASK)))[0]
    estimate = (d2 - 1.5) * 0.289529654 + 0.176091259 + bin_exp * 0.301029995663981
    return math.floor(estimate)


def _roundup(digits: list[int]) -> int:
    """Add one to the last digit. Returns 1 when the carry ran off the front."""
    i = len(digits) - 1
    if digits[i] == 9:
        while digits[i] == 9 and i > 0:
            digits[i] = 0
            i -= 1
        if digits[i] == 9:
            digits[0] = 1
            return 1
    digits[i] += 1
    return 0
