"""2009 TSV models: scalar functions, SI arguments/returns unless stated.

Empirical factors use numeric micrometer values. Defaults retain 2009 constants.
Capacitance conventions are required explicitly because the source units disagree.
Inductance mode is 'dc' or 'asymptotic'; no transition-frequency model is implied.
"""
from math import pi, sqrt, log, exp, isfinite

EPS0 = 8.85e-12
EPS_SI = 11.7 * EPS0
EPS_OX = 3.9 * EPS0
MU0 = 4 * pi * 1e-7
SIGMA_W = 1.82e7


def _positive(**values):
    for name, value in values.items():
        if not isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive')


def _mode(mode):
    if mode not in ('dc', 'asymptotic'):
        raise ValueError("mode must be 'dc' or 'asymptotic'")


def skin_depth(frequency_hz, conductivity=SIGMA_W):
    _positive(frequency=frequency_hz, conductivity=conductivity)
    return 1 / sqrt(pi * frequency_hz * MU0 * conductivity)


def resistance_dc(length_m, diameter_m, conductivity=SIGMA_W):
    _positive(length=length_m, diameter=diameter_m, conductivity=conductivity)
    return length_m / (conductivity * pi * (diameter_m / 2)**2)


def resistance(length_m, diameter_m, frequency_hz=0):
    """Tungsten fit at 1 GHz, then square-root frequency adjustment (ohms).

    Fit coefficients were calibrated for tungsten, so conductivity is fixed here.
    """
    _positive(length=length_m, diameter=diameter_m)
    if not isfinite(frequency_hz) or frequency_hz < 0:
        raise ValueError('frequency must be finite and nonnegative')
    dc = resistance_dc(length_m, diameter_m)
    if frequency_hz == 0:
        return dc
    r = diameter_m / 2
    delta = skin_depth(1e9)
    d_um = diameter_m * 1e6
    ar = length_m / diameter_m
    if delta < r:
        alpha = .0472*d_um**.2831*log(ar) + 2.4712*d_um**(-.269)
        area = pi * (2*r*delta-delta**2)
    else:
        alpha = .0091*d_um**1.0806*log(ar) + 1.0518*d_um**.092
        area = pi*r*r
    r1 = alpha * length_m / (SIGMA_W * area)
    return dc + (r1-dc) * sqrt(frequency_hz/1e9)


def self_inductance(length_m, diameter_m, mode='dc'):
    _positive(length=length_m, diameter=diameter_m)
    _mode(mode)
    h, r, ar = length_m, diameter_m/2, length_m/diameter_m
    if mode == 'dc':
        alpha = 1-exp(-4.3*ar)
        return alpha*MU0/(2*pi)*(h*log((h+sqrt(h*h+r*r))/r)+r-sqrt(h*h+r*r)+h/4)
    alpha = .94+.52*exp(-10*abs(ar-1))
    return alpha*MU0*h/(2*pi)*abs(log(2*h/r)-1)


def _mutual_base(length_m, pitch_m):
    return MU0/(2*pi)*(length_m*log((length_m+sqrt(length_m**2+pitch_m**2))/pitch_m)+pitch_m-sqrt(length_m**2+pitch_m**2))


def mutual_inductance(length_m, diameter_m, pitch_m, mode='dc'):
    """Equal lengths; pitch is center-to-center distance, not edge spacing."""
    _positive(length=length_m, diameter=diameter_m, pitch=pitch_m)
    _mode(mode)
    if pitch_m <= diameter_m:
        raise ValueError('pitch must exceed diameter')
    beta = 1 if mode == 'dc' else .1535*log(length_m/diameter_m)+.592
    return beta*_mutual_base(length_m, pitch_m)


def mutual_inductance_unequal(short_length_m, long_length_m, diameter_m, pitch_m, mode='dc'):
    _positive(short_length=short_length_m, long_length=long_length_m, diameter=diameter_m, pitch=pitch_m)
    _mode(mode)
    if long_length_m < short_length_m or pitch_m <= diameter_m:
        raise ValueError('long length must be >= short length; pitch must exceed diameter')
    h, h2, d = short_length_m, long_length_m, diameter_m
    ar = h/d
    alpha = .8+.1945*((pitch_m-d)/d)**.52
    beta1 = 2.1+4*exp(-.375*ar-.1)
    beta2 = exp(-.21*ar+.6)-.57
    beta = beta1-2*exp(-.3*h2/h+beta2)
    gamma = 1 if mode == 'dc' else .955-1.1*exp(-.75-.5*ar)
    return alpha*beta*gamma*_mutual_base(h, pitch_m)


def capacitance_ground(length_m, diameter_m, ground_spacing_m, liner_m=1e-6,
                       *, convention, acceptors_cm3=1e15, intrinsic_cm3=1.5e10, temperature_k=300):
    """Farads. Required convention: 'legacy_matlab', 'si_oxide', 'si_silicon'.

    legacy_matlab reproduces mixed-unit C_min_adj, NOT a physical SI correction.
    si_* converts cm^-3 to m^-3 and uses true sidewall area. Numerator selects
    oxide (MATLAB and published PDF) or silicon (old LaTeX draft). Fits have NOT been recalibrated.
    """
    _positive(length=length_m, diameter=diameter_m, ground_spacing=ground_spacing_m,
              liner=liner_m, acceptors=acceptors_cm3, intrinsic=intrinsic_cm3, temperature=temperature_k)
    if acceptors_cm3 <= intrinsic_cm3:
        raise ValueError('depletion model requires acceptors > intrinsic concentration')
    if convention not in ('legacy_matlab', 'si_oxide', 'si_silicon'):
        raise ValueError('unknown capacitance convention')
    legacy = convention == 'legacy_matlab'
    na = acceptors_cm3 if legacy else acceptors_cm3*1e6
    phi = (1.38e-23*temperature_k/1.6e-19)*log(acceptors_cm3/intrinsic_cm3)
    xd = sqrt(4*EPS_SI*phi/(1.6e-19*na))
    area = pi*diameter_m*length_m*(100 if legacy else 1)
    numerator = EPS_SI if convention == 'si_silicon' else EPS_OX
    ar, d_um, g_um = length_m/diameter_m, diameter_m*1e6, ground_spacing_m*1e6
    alpha = (-.0351*ar+1.5701)*g_um**(.0111*ar-.1997)
    beta = 5.8934*d_um**(-.553)*ar**(-(.0031*d_um+.43))
    return alpha*beta*numerator*area/(liner_m+(EPS_OX/EPS_SI)*xd)


def capacitance_coupling(length_m, diameter_m, edge_spacing_m, ground_spacing_m, *, convention):
    """Farads. 'published' vs 'matlab_candidate' differ in gamma for S/D > 1.

    Candidate is the COMMENTED MATLAB large-spacing branch; not certified.
    """
    _positive(length=length_m, diameter=diameter_m, edge_spacing=edge_spacing_m, ground_spacing=ground_spacing_m)
    if convention not in ('published', 'matlab_candidate'):
        raise ValueError('unknown coupling convention')
    h, d, s = length_m, diameter_m, edge_spacing_m
    ar, s_um, g_um = h/d, s*1e6, ground_spacing_m*1e6
    alpha = .225*log(.97*ar)+.53
    beta = .5711*ar**(-.988)*log(g_um)+(.85-exp(-ar+1.3))
    gamma = 1
    if s/d > 1+1e-12:
        z = .5+abs((s+d)/d-4)
        if convention == 'published':
            gamma = (1+exp(-z*ar))*(log(ar+4*exp(-s_um/9)+2.9)-10.625*s_um**(-.51))
        else:
            gamma = (1+exp(-z*ar))*(log(ar+4*exp(-s_um/9+5.1)+2.9)-10.625*s_um**(-.507))
    return .4*alpha*beta*gamma*EPS_SI*pi*d*h/s


def sakurai_normalized(width_ratio, thickness_ratio, spacing_ratio):
    """Return C1/epsilon and C2/epsilon from archived exploratory scripts."""
    _positive(width_ratio=width_ratio, thickness_ratio=thickness_ratio, spacing_ratio=spacing_ratio)
    w, t, s = width_ratio, thickness_ratio, spacing_ratio
    c1 = 1.15*w+2.8*t**.222
    c2 = c1+2*(.03*w+.83*t-.07*t**.222)*s**(-1.34)
    return c1, c2


def pdn_via_count(current_a, current_density_a_cm2, diameter_um, integer_count=True):
    """Count and area penalty (um^2) assuming pitch = 2*diameter."""
    from math import ceil
    _positive(current=current_a, current_density=current_density_a_cm2, diameter=diameter_um)
    count = (current_a/current_density_a_cm2)/(pi*(diameter_um*1e-4/2)**2)
    if integer_count:
        count = ceil(count)
    return count, (2*diameter_um)**2*count
