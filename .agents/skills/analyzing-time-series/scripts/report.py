#!/usr/bin/env python3
"""
Time Series Diagnostic Report

Assembles diagnostics.json + plots/ into a single self-contained PDF, where
every number is followed by the plain-language reason it matters.

Run diagnose.py (and ideally visualize.py) first.
"""

import argparse
import json
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.image import imread

# Page geometry (inches, US Letter portrait).
PAGE = (8.5, 11)
BODY_X = 0.08
BODY_TOP = 0.90
LINE = 0.022

# Plots are embedded in this order, one per page. Missing files are skipped,
# so the report still builds if visualize.py was never run.
PLOT_ORDER = [
    ('timeseries.png', 'The raw series. Look for level shifts, outliers, and whether swings grow with the level.'),
    ('decomposition.png', 'STL splits the series into trend, a repeating seasonal cycle, and the residual left over. A residual with visible structure means the split missed something.'),
    ('acf_pacf.png', 'ACF/PACF on the differenced series. Bars outside the shaded band are real correlation, and their positions suggest the AR and MA orders.'),
    ('rolling_stats.png', 'Rolling mean and standard deviation. A drifting mean means non-stationary; a fanning standard deviation is what a transform fixes.'),
    ('histogram.png', 'Value distribution. Strong right skew is the usual sign that a log or sqrt transform will help.'),
    ('box_by_quarter.png', 'Values grouped by quarter. Boxes sitting at clearly different heights confirm seasonality.'),
    ('box_by_month.png', 'Values grouped by month.'),
    ('box_by_dayofweek.png', 'Values grouped by day of week.'),
    ('lag_scatter.png', 'Each value against its own past. A tight diagonal means that lag carries real predictive signal.'),
]


def wrap(text, width=96):
    """Wrap a paragraph, preserving deliberate blank lines."""
    out = []
    for para in text.split('\n'):
        out.extend(textwrap.wrap(para, width=width) or [''])
    return out


class Report:
    """Accumulates text onto pages, spilling to a new page when full."""

    def __init__(self, pdf):
        self.pdf = pdf
        self.fig = None
        self.y = 0

    def _new_page(self):
        self.flush()
        self.fig = plt.figure(figsize=PAGE)
        self.y = BODY_TOP

    def flush(self):
        if self.fig is not None:
            self.pdf.savefig(self.fig)
            plt.close(self.fig)
            self.fig = None

    def _room(self, lines):
        """Start a new page unless `lines` more lines fit below the margin.

        Blocks are kept whole rather than split across pages: a finding whose
        explanation lands on the next page reads as orphaned.
        """
        if self.fig is None or self.y - lines * LINE < 0.05:
            self._new_page()

    def text(self, s, size=9.5, weight='normal', color='#222222', indent=0.0, gap=1.0):
        lines = wrap(s)
        self._room(len(lines) + gap)
        for line in lines:
            self.fig.text(BODY_X + indent, self.y, line, size=size,
                          weight=weight, color=color, family='DejaVu Sans')
            self.y -= LINE
        self.y -= LINE * (gap - 1)

    def heading(self, s):
        self._room(4)
        self.y -= LINE * 0.5
        self.fig.text(BODY_X, self.y, s, size=13, weight='bold', color='#111111')
        self.y -= LINE * 0.4
        self.fig.add_artist(plt.Line2D([BODY_X, 0.92], [self.y, self.y],
                                       color='#cccccc', linewidth=0.8))
        self.y -= LINE * 1.1

    def finding(self, label, value, why):
        """A measured value plus the reason it matters."""
        self._room(len(wrap(why)) + 3)
        self.fig.text(BODY_X, self.y, f'{label}:', size=10, weight='bold', color='#111111')
        self.fig.text(BODY_X + 0.30, self.y, str(value), size=10,
                      color='#1f77b4', weight='bold')
        self.y -= LINE * 1.15
        self.text(why, size=9, color='#444444', indent=0.015, gap=1.6)


def fmt(x, nd=4):
    return f'{x:.{nd}f}' if isinstance(x, float) else str(x)


def p_value(p):
    """p-values round to 0.0 in the JSON; report the bound instead of a false zero."""
    return '< 0.0001' if isinstance(p, float) and p < 0.0001 else fmt(p)


def cover(rep, d, source, value_col):
    q, dist = d['data_quality'], d['distribution']
    rep._new_page()
    rep.fig.text(BODY_X, 0.94, 'Time Series Diagnostic Report',
                 size=20, weight='bold', color='#111111')
    rep.y = 0.89
    rep.text(f'Source: {source}', size=9, color='#666666', gap=0.6)
    rep.text(f'Series: {value_col}', size=9, color='#666666', gap=1.4)

    rep.heading('Verdict')
    st, se, tr, fc, tx = (d['stationarity'], d['seasonality'],
                          d['trend'], d['forecastability'], d['transform'])
    verdict = [
        ('Forecastable', 'Yes' if fc['forecastable'] else 'No — behaves like noise'),
        ('Stationary', 'Yes' if st['adf_stationary'] and st['kpss_stationary']
         else f"No (difference d={st['differencing_needed']})"),
        ('Seasonal', f"Yes, period {se['period']}" if se['is_seasonal'] else 'No'),
        ('Trend', tr['direction'].capitalize() if tr['has_trend'] else 'None'),
        ('Transform', f"{tx['recommendation']}" if tx['recommendation'] != 'none' else 'None needed'),
    ]
    for k, v in verdict:
        rep._room(2)
        rep.fig.text(BODY_X, rep.y, f'{k}:', size=10.5, weight='bold')
        rep.fig.text(BODY_X + 0.30, rep.y, v, size=10.5, color='#1f77b4', weight='bold')
        rep.y -= LINE * 1.25

    rep.y -= LINE
    order = suggested_model(d)
    rep.text(f'Suggested starting model: {order}', size=10,
             weight='bold', color='#111111', gap=1.6)

    rep.heading('Data quality')
    rep.text(f"{q['n_observations']} observations, {q['frequency']}, "
             f"{q['date_start']} to {q['date_end']}. "
             f"Missing values: {q['missing_values']} ({q['missing_pct']}%).", gap=1.4)
    rep.text(f"Mean {fmt(dist['mean'], 2)}   Median {fmt(dist['median'], 2)}   "
             f"Std {fmt(dist['std'], 2)}   Min {fmt(dist['min'], 2)}   "
             f"Max {fmt(dist['max'], 2)}", size=9, color='#444444', gap=1.2)
    rep.text(f"Skewness {fmt(dist['skewness'])} — "
             f"{'roughly symmetric' if abs(dist['skewness']) < 0.5 else 'noticeably skewed, which is why a transform is worth considering'}. "
             f"Kurtosis {fmt(dist['kurtosis'])}.", size=9, color='#444444')


def suggested_model(d):
    """Translate the diagnostics into a starting ARIMA/SARIMA specification."""
    dd = d['stationarity']['differencing_needed']
    tx = d['transform']['recommendation']
    base = f'ARIMA(p,{dd},q)'
    if d['seasonality']['is_seasonal']:
        base = f"SARIMA(p,{dd},q)(P,1,Q)[{d['seasonality']['period']}]"
    if tx and tx != 'none':
        base += f' on {tx}(series)'
    return base


def explain_stationarity(rep, st):
    rep.heading('Stationarity')
    rep.text('A model can only assume the future looks like the past if the series has a stable '
             'mean and variance. Two tests are run because they disagree in a useful way: ADF asks '
             '"is there a unit root?" and KPSS asks "is this stable around a level?". Agreement '
             'is strong evidence; disagreement usually means a trend rather than a random walk.',
             size=9, color='#444444', gap=1.6)
    rep.finding('ADF statistic', fmt(st['adf_statistic']),
                f"p = {p_value(st['adf_p_value'])}. "
                + ('Below 0.05, so the unit-root hypothesis is rejected — this test calls the series stationary.'
                   if st['adf_stationary'] else
                   'Above 0.05, so a unit root cannot be ruled out: the series wanders rather than reverting to a mean.'))
    rep.finding('KPSS statistic', fmt(st['kpss_statistic']),
                f"p = {p_value(st['kpss_p_value'])}. "
                + ('Above 0.05, so stationarity around a level is not rejected.'
                   if st['kpss_stationary'] else
                   'At or below 0.05, so stability around a fixed level is rejected — consistent with a trend or drift.'))
    rep.finding('Differencing needed', f"d = {st['differencing_needed']}",
                'This is the number of times to subtract the previous value before modelling. '
                + ('The series is already stationary, so no differencing is applied.'
                   if st['differencing_needed'] == 0 else
                   f"Differencing {st['differencing_needed']}x removes the drift and is what the ACF/PACF plot is computed on. "
                   + ('The result was re-tested and confirmed stationary.'
                      if st.get('differencing_verified') else
                      'Note: the differenced series did not fully pass re-testing — inspect the rolling-statistics plot before committing to this d.')))


def explain_seasonality(rep, se, freq):
    rep.heading('Seasonality')
    rep.text('Seasonality is a cycle that repeats at a fixed, known period. It is measured here by '
             'STL decomposition: the share of variation the repeating component explains, once the '
             'trend is removed. Strength runs 0 to 1.', size=9, color='#444444', gap=1.6)
    if not se['is_seasonal']:
        rep.finding('Seasonal', 'No',
                    'No repeating cycle strong enough to model. A plain ARIMA is sufficient; '
                    'adding seasonal terms would spend parameters on noise.')
        return
    s = se['strength']
    band = ('strong — the cycle is a dominant feature and a seasonal model term is mandatory'
            if s >= 0.64 else
            'moderate — worth modelling, but check whether it is stable over the whole history'
            if s >= 0.3 else
            'weak — borderline; compare a seasonal and non-seasonal model before committing')
    rep.finding('Period', f"{se['period']} ({freq} data)",
                f"The cycle repeats every {se['period']} observations, which for {freq} data is a "
                "full calendar year. Seasonal model terms are indexed on this number.")
    rep.finding('Seasonal strength', fmt(s), f'{band}.')


def explain_trend(rep, tr):
    rep.heading('Trend')
    rep.text('Trend is the slow movement of the level, separated from the repeating cycle by the '
             'same STL decomposition. A strong trend is the main reason a series is non-stationary '
             'and therefore why differencing is needed.', size=9, color='#444444', gap=1.6)
    if not tr['has_trend']:
        rep.finding('Trend', 'None detected',
                    'The level is flat over the sample. Any apparent movement is cycle or noise.')
        return
    rep.finding('Direction', tr['direction'],
                f"The level is {tr['direction']} over the sample. Forecasts will extrapolate this, "
                "so satisfy yourself that the driver behind it still holds over the horizon — this "
                "is a judgement the statistics cannot make for you.")
    rep.finding('Trend strength', fmt(tr['strength']),
                'Share of non-seasonal variation explained by the trend. '
                + ('Above 0.64 counts as strong: the trend dominates, and differencing is doing most of the work.'
                   if tr['strength'] >= 0.64 else 'Moderate — the trend is real but not dominant.'))
    if 'slope_normalized' in tr:
        rep.finding('Normalized slope', fmt(tr['slope_normalized'], 6),
                    'Average change per period, scaled by the series level, so it is comparable '
                    'across series of different magnitudes.')


def explain_forecastability(rep, fc):
    rep.heading('Forecastability')
    rep.text('Before fitting anything, it is worth knowing whether there is structure to fit. The '
             'Ljung-Box test asks whether the autocorrelations up to a given lag are jointly zero. '
             'A small p-value means they are not — past values carry information about future ones, '
             'so a model can beat a naive guess.', size=9, color='#444444', gap=1.6)
    for lag, res in sorted(fc['ljung_box_results'].items(),
                           key=lambda kv: int(kv[0].split('_')[1])):
        n = lag.split('_')[1]
        rep.finding(f'Ljung-Box (lag {n})', f"stat {fmt(res['statistic'], 2)}, p {p_value(res['p_value'])}",
                    'Structure detected — autocorrelation at these lags is not zero.'
                    if res['p_value'] < 0.05 else
                    'No structure detected at this lag.')
    rep.finding('Verdict', 'Forecastable' if fc['forecastable'] else 'Not forecastable',
                'The series is not white noise: a fitted model should outperform a naive forecast.'
                if fc['forecastable'] else
                'The series is statistically indistinguishable from noise. No model will reliably '
                'beat the last value or the mean — say so rather than shipping a model that looks busy.')


def explain_autocorrelation(rep, ac, st):
    rep.heading('Autocorrelation (model order)')
    rep.text('ACF and PACF are how the AR and MA orders get chosen. Read on the differenced series: '
             'the ACF tail suggests the MA order q, and the PACF cut-off suggests the AR order p. '
             'Only lags outside the confidence band count as real.', size=9, color='#444444', gap=1.6)
    rep.finding('Series analysed', st.get('series_used_for_acf', 'original'),
                'Autocorrelation is only meaningful on a stationary series, so the plots use this version.')
    rep.finding('Confidence threshold', fmt(ac['confidence_threshold']),
                'Correlations smaller than this in absolute value are indistinguishable from zero '
                'at this sample size.')
    rep.finding('Significant ACF lags', ac['significant_acf_lags'] or 'none',
                'Candidate MA terms. Spikes at multiples of the seasonal period indicate a seasonal '
                'MA term rather than a long non-seasonal one.')
    rep.finding('Significant PACF lags', ac['significant_pacf_lags'] or 'none',
                'Candidate AR terms. Start at the low end: the first few lags usually carry most of '
                'the signal, and extra terms cost degrees of freedom.')


def explain_transform(rep, tx):
    rep.heading('Variance transform')
    rep.text('ARIMA assumes the size of the wobble does not depend on the level of the series. When '
             'swings grow as the series grows, a transform is applied first. Box-Cox estimates the '
             'exponent that best stabilizes the variance.', size=9, color='#444444', gap=1.6)
    rep.finding('Variance stable', 'Yes' if tx['variance_stable'] else 'No',
                'Spread is constant across the sample; no transform needed.'
                if tx['variance_stable'] else
                'Spread grows with the level, so residuals from an untransformed model would be '
                'heteroscedastic and the prediction intervals too narrow at the high end.')
    if tx.get('boxcox_lambda') is not None:
        lam = tx['boxcox_lambda']
        near = ('near 0, which corresponds to a log transform' if abs(lam) < 0.25 else
                'near 0.5, which corresponds to a square-root transform' if abs(lam - 0.5) < 0.25 else
                'near 1, meaning no transform is required' if abs(lam - 1) < 0.25 else
                'in an intermediate range')
        rep.finding('Box-Cox lambda', fmt(lam),
                    f'The optimal exponent is {near}. Rounding to a standard transform is usually '
                    'preferred over the exact value — it keeps the model interpretable and the '
                    'back-transform simple.')
    rep.finding('Recommendation', tx['recommendation'],
                'Apply this to the series before fitting, and remember to invert it on the '
                'forecasts and on both prediction-interval bounds.'
                if tx['recommendation'] != 'none' else
                'Model the series as-is.')


def next_steps(rep, d):
    rep.heading('Suggested next steps')
    st, se, fc = d['stationarity'], d['seasonality'], d['forecastability']
    steps = []
    if not fc['forecastable']:
        steps.append('The series shows no exploitable structure. Use a naive or mean forecast as '
                     'the baseline and treat any more complex model with suspicion.')
    else:
        if d['transform']['recommendation'] != 'none':
            steps.append(f"Apply the {d['transform']['recommendation']} transform first, and invert "
                         'it on forecasts and interval bounds.')
        steps.append(f"Start from {suggested_model(d)} and refine p and q from the ACF/PACF plot.")
        if se['is_seasonal']:
            steps.append(f"Include seasonal differencing (D=1) at period {se['period']}: ordinary "
                         'differencing alone will not clear correlation at the seasonal lags.')
        steps.append('Hold out the most recent observations for validation rather than judging fit '
                     'on the training sample — in-sample fit always flatters the model.')
        steps.append('Check the residuals after fitting: they should pass Ljung-Box, meaning no '
                     'structure was left on the table.')
    for i, s in enumerate(steps, 1):
        rep.text(f'{i}.  {s}', size=9.5, color='#333333', gap=1.4)


def add_plots(pdf, plots_dir):
    """One plot per page, each with the caption explaining what to look for."""
    if not plots_dir.is_dir():
        return 0
    n = 0
    for name, caption in PLOT_ORDER:
        path = plots_dir / name
        if not path.exists():
            continue
        fig = plt.figure(figsize=PAGE)
        fig.text(BODY_X, 0.95, name.replace('.png', '').replace('_', ' ').title(),
                 size=13, weight='bold', color='#111111')
        for i, line in enumerate(wrap(caption, width=92)):
            fig.text(BODY_X, 0.915 - i * 0.018, line, size=9, color='#555555')
        ax = fig.add_axes([0.06, 0.08, 0.88, 0.76])
        ax.imshow(imread(path))
        ax.axis('off')
        pdf.savefig(fig)
        plt.close(fig)
        n += 1
    return n


def main():
    parser = argparse.ArgumentParser(
        description='Assemble diagnostics.json and plots into an explained PDF report.')
    parser.add_argument('--output-dir', default='diagnostics',
                        help='Directory holding diagnostics.json and plots/ (default: diagnostics)')
    parser.add_argument('--output-file', default=None,
                        help='PDF path (default: <output-dir>/report.pdf)')
    parser.add_argument('--source', default='(not recorded)',
                        help='Input data path, printed on the cover page')
    parser.add_argument('--value-col', default='(auto-detected)',
                        help='Series name, printed on the cover page')
    args = parser.parse_args()

    out = Path(args.output_dir)
    diag_file = out / 'diagnostics.json'
    if not diag_file.exists():
        raise SystemExit(f'No diagnostics.json in {out}/ — run diagnose.py first.')

    with open(diag_file, encoding='utf-8') as f:
        d = json.load(f)

    pdf_path = Path(args.output_file) if args.output_file else out / 'report.pdf'
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(pdf_path) as pdf:
        rep = Report(pdf)
        cover(rep, d, args.source, args.value_col)
        explain_stationarity(rep, d['stationarity'])
        explain_seasonality(rep, d['seasonality'], d['data_quality']['frequency'])
        explain_trend(rep, d['trend'])
        explain_forecastability(rep, d['forecastability'])
        explain_autocorrelation(rep, d['autocorrelation'], d['stationarity'])
        explain_transform(rep, d['transform'])
        next_steps(rep, d)
        rep.flush()
        n_plots = add_plots(pdf, out / 'plots')

        meta = pdf.infodict()
        meta['Title'] = f'Time Series Diagnostics — {args.value_col}'
        meta['Subject'] = f'Diagnostic report for {args.source}'

    print(f'Report written to: {pdf_path}')
    if n_plots:
        print(f'  {n_plots} plot page(s) embedded')
    else:
        print('  No plots embedded — run visualize.py first for the visual pages')


if __name__ == '__main__':
    main()
