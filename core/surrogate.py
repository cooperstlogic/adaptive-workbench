"""Two model recipes, cross-validated against each other every round.

``ridge_onehot`` is ridge regression over the one-hot block, read as Bayesian
linear regression so the predictive variance is analytic rather than bolted
on. ``gp_pca64`` is an exact Gaussian process with an RBF kernel over the
first 64 principal components of the active feature block, its two
hyperparameters chosen by grid search against the marginal likelihood.

Only affinity is measured, so there is exactly one surrogate per round and the
bake-off is between recipes rather than across objectives. The winner is the
recipe with the best held-out *calibrated* performance, which is a single
number -- held-out negative log predictive density -- rather than accuracy with
calibration inspected afterwards. Root-mean-square error, R-squared and
interval coverage are recorded alongside it so a human can see why.

Censored wells enter the fit at the detection limit carrying a flag. That
biases them slightly upward and is the boring choice; the alternative is a
Tobit likelihood and it is not worth the hour.
"""

import numpy as np

from . import encode, schema

RECIPES = ("ridge_onehot", "gp_pca64")
DEFAULT_COMPONENTS = 64
CV_FOLDS = 5
CV_SHUFFLE_SEED = 12345

# --- Gaussian helpers ------------------------------------------------------
# numpy has no erf and scipy is not a dependency, so the error function is the
# Abramowitz and Stegun 7.1.26 rational form: pure float64 arithmetic, maximum
# absolute error 1.5e-7, and identical on a laptop and under WebAssembly --
# which matters because these numbers are hashed into batch records.

_AS = (0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429)
_AS_P = 0.3275911

# Half-widths of central probability intervals, to avoid an inverse-normal
# approximation for the two values this build ever needs.
Z_CENTRAL = {0.80: 1.2815515655446004, 0.90: 1.6448536269514722, 0.95: 1.959963984540054}


def erf(x):
    x = np.asarray(x, dtype=np.float64)
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + _AS_P * a)
    poly = (((((_AS[4] * t) + _AS[3]) * t + _AS[2]) * t + _AS[1]) * t + _AS[0]) * t
    return s * (1.0 - poly * np.exp(-a * a))


def norm_cdf(z):
    return 0.5 * (1.0 + erf(np.asarray(z, dtype=np.float64) / np.sqrt(2.0)))


def norm_pdf(z):
    z = np.asarray(z, dtype=np.float64)
    return np.exp(-0.5 * z * z) / np.sqrt(2.0 * np.pi)


def z_for_central(p):
    if p not in Z_CENTRAL:
        raise ValueError("no tabulated z for a central %r interval" % (p,))
    return Z_CENTRAL[p]


# --- shared feature context ------------------------------------------------


class Features:
    """One-hot block over a fixed candidate pool, plus its PCA.

    Built once per pool and reused across rounds: the pool does not move, so
    neither does its principal basis, and recomputing it each round would only
    add cost and a way for two surfaces to disagree.
    """

    def __init__(self, pool, editable_region, n_components=DEFAULT_COMPONENTS):
        self.pool = list(pool)
        self.index = {s: i for i, s in enumerate(self.pool)}
        self.editable_region = list(editable_region)
        self.block = "onehot"
        self.X = encode.one_hot(self.pool, editable_region).astype(np.float64)
        self.mean = self.X.mean(axis=0)
        Xc = self.X - self.mean
        _, sv, vt = np.linalg.svd(Xc, full_matrices=False)
        k = int(min(n_components, vt.shape[0]))
        self.n_components = k
        self.components = vt[:k]
        self.Z = Xc @ self.components.T
        total = float((sv ** 2).sum())
        self.explained_variance_ratio = float((sv[:k] ** 2).sum() / total) if total > 0 else 0.0

    def rows(self, sequences):
        try:
            return np.array([self.index[s] for s in sequences], dtype=np.int64)
        except KeyError as exc:
            raise KeyError("sequence is not in the candidate pool: %s" % exc.args[0])

    def onehot(self, sequences):
        return self.X[self.rows(sequences)]

    def pcs(self, sequences):
        return self.Z[self.rows(sequences)]


# --- ridge_onehot ----------------------------------------------------------


def _ridge_grid(n_features):
    alphas = np.logspace(-2.0, 3.0, 11)
    sigmas = np.array([0.05, 0.1, 0.15, 0.25, 0.4, 0.7, 1.2])
    return alphas, sigmas


def fit_ridge_onehot(X, y):
    """Bayesian linear regression, hyperparameters by log marginal likelihood.

    The eigendecomposition of X'X is taken once and every point on the grid is
    then O(d^2), which is what keeps a twenty-seed campaign under a minute.
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n, d = X.shape
    y_mean = float(y.mean())
    yc = y - y_mean
    gram = X.T @ X
    b = X.T @ yc
    w, V = np.linalg.eigh(gram)
    w = np.maximum(w, 0.0)
    bv = V.T @ b
    yy = float(yc @ yc)

    alphas, sigmas = _ridge_grid(d)
    best = None
    for s in sigmas:
        s2 = float(s * s)
        for a in alphas:
            lam = a + w / s2
            mv = bv / (s2 * lam)
            rss = yy - 2.0 * float(mv @ bv) + float((mv * mv * w).sum())
            mm = float((mv * mv).sum())
            logml = (
                -0.5 * n * np.log(2.0 * np.pi * s2)
                + 0.5 * d * np.log(a)
                - 0.5 * float(np.log(lam).sum())
                - rss / (2.0 * s2)
                - a * mm / 2.0
            )
            if best is None or logml > best[0]:
                best = (float(logml), float(a), s2, lam, mv)

    logml, alpha, s2, lam, mv = best
    return {
        "recipe": "ridge_onehot",
        "y_mean": y_mean,
        "m": V @ mv,
        "V": V,
        "lam": lam,
        "sigma2": s2,
        "alpha": alpha,
        "log_marginal_likelihood": logml,
        "hyperparameters": {"alpha": alpha, "noise_sd": float(np.sqrt(s2))},
    }


def predict_ridge_onehot(model, X):
    """-> (mean, sd) of the *measurement* a lab would report, noise included.

    Predicting the observation rather than the latent function is what makes
    the interval coverage below comparable to what actually comes back, and it
    is the quantity the batch table shows a scientist.
    """
    X = np.asarray(X, dtype=np.float64)
    mu = X @ model["m"] + model["y_mean"]
    proj = X @ model["V"]
    var = model["sigma2"] + ((proj * proj) / model["lam"]).sum(axis=1)
    return mu, np.sqrt(np.maximum(var, 1e-12))


# --- gp_pca64 --------------------------------------------------------------


def _sqdist(A, B):
    a2 = (A * A).sum(axis=1)[:, None]
    b2 = (B * B).sum(axis=1)[None, :]
    return np.maximum(a2 + b2 - 2.0 * (A @ B.T), 0.0)


def _gp_grid(d2):
    off = d2[np.triu_indices_from(d2, k=1)] if d2.shape[0] > 1 else np.array([1.0])
    med = float(np.sqrt(np.median(off))) if off.size else 1.0
    med = med if med > 1e-9 else 1.0
    lengthscales = med * np.array([0.25, 0.5, 1.0, 2.0, 4.0, 8.0])
    noises = np.array([0.05, 0.1, 0.15, 0.25, 0.4])
    return lengthscales, noises


def fit_gp_pca64(Z, y):
    """Exact GP, RBF kernel, two hyperparameters by grid search on the evidence.

    Lengthscales are multiples of the median pairwise distance in the reduced
    space, so the grid means the same thing whatever the principal components
    are scaled like.
    """
    Z = np.asarray(Z, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = Z.shape[0]
    y_mean = float(y.mean())
    yc = y - y_mean
    sf2 = float(max(np.var(yc), 1e-6))
    d2 = _sqdist(Z, Z)
    lengthscales, noises = _gp_grid(d2)

    best = None
    eye = np.eye(n)
    for ell in lengthscales:
        k0 = sf2 * np.exp(-d2 / (2.0 * ell * ell))
        for sn in noises:
            K = k0 + (sn * sn + 1e-8) * eye
            sign, logdet = np.linalg.slogdet(K)
            if sign <= 0:
                continue
            try:
                alpha = np.linalg.solve(K, yc)
            except np.linalg.LinAlgError:
                continue
            logml = -0.5 * float(yc @ alpha) - 0.5 * float(logdet) - 0.5 * n * np.log(2.0 * np.pi)
            if best is None or logml > best[0]:
                best = (float(logml), float(ell), float(sn), K, alpha)

    logml, ell, sn, K, alpha = best
    return {
        "recipe": "gp_pca64",
        "Z": Z,
        "y_mean": y_mean,
        "sf2": sf2,
        "lengthscale": ell,
        "noise_sd": sn,
        "alpha": alpha,
        "K_inv": np.linalg.inv(K),
        "log_marginal_likelihood": logml,
        "hyperparameters": {"lengthscale": ell, "noise_sd": sn, "signal_var": sf2},
    }


def predict_gp_pca64(model, Z, chunk=2048):
    Z = np.asarray(Z, dtype=np.float64)
    mus, sds = [], []
    sf2, ell = model["sf2"], model["lengthscale"]
    noise2 = model["noise_sd"] ** 2
    for i in range(0, Z.shape[0], chunk):
        block = Z[i : i + chunk]
        Ks = sf2 * np.exp(-_sqdist(block, model["Z"]) / (2.0 * ell * ell))
        mus.append(Ks @ model["alpha"] + model["y_mean"])
        var = sf2 + noise2 - ((Ks @ model["K_inv"]) * Ks).sum(axis=1)
        sds.append(np.sqrt(np.maximum(var, 1e-12)))
    return np.concatenate(mus), np.concatenate(sds)


_FIT = {"ridge_onehot": fit_ridge_onehot, "gp_pca64": fit_gp_pca64}
_PREDICT = {"ridge_onehot": predict_ridge_onehot, "gp_pca64": predict_gp_pca64}


def _design_matrix(features, sequences, recipe):
    return features.onehot(sequences) if recipe == "ridge_onehot" else features.pcs(sequences)


# --- cross-validation and the bake-off -------------------------------------


def _folds(n, k, seed=CV_SHUFFLE_SEED):
    k = int(max(2, min(k, n)))
    idx = np.random.default_rng(seed).permutation(n)
    return [idx[i::k] for i in range(k)]


def cross_validate(features, sequences, y, recipe, folds=CV_FOLDS, interval=0.80):
    """Held-out accuracy and calibration for one recipe.

    Hyperparameters are re-selected inside every fold. Choosing them once on
    all the data and then scoring the same data held out would report a number
    the round cannot deliver.
    """
    y = np.asarray(y, dtype=np.float64)
    n = len(sequences)
    D = _design_matrix(features, sequences, recipe)
    z = z_for_central(interval)
    pred_mu = np.zeros(n)
    pred_sd = np.zeros(n)
    for fold in _folds(n, folds):
        mask = np.ones(n, dtype=bool)
        mask[fold] = False
        if mask.sum() < 3:
            continue
        model = _FIT[recipe](D[mask], y[mask])
        mu, sd = _PREDICT[recipe](model, D[fold])
        pred_mu[fold] = mu
        pred_sd[fold] = sd

    resid = y - pred_mu
    sd = np.maximum(pred_sd, 1e-9)
    var_y = float(np.var(y))
    nlpd = float(np.mean(0.5 * np.log(2.0 * np.pi * sd * sd) + (resid * resid) / (2.0 * sd * sd)))
    return {
        "recipe": recipe,
        "folds": int(min(folds, n)),
        "n": int(n),
        "rmse": float(np.sqrt(np.mean(resid * resid))),
        "r2": float(1.0 - np.mean(resid * resid) / var_y) if var_y > 0 else 0.0,
        "coverage_80": float(np.mean(np.abs(resid) <= z * sd)),
        "interval": float(interval),
        "nlpd": nlpd,
        "mean_pred_sd": float(np.mean(sd)),
    }


def fit_surrogates(features, observations, recipes=RECIPES, folds=CV_FOLDS, predict_pool=True):
    """Fit every registered recipe, cross-validate, pick a winner.

    ``observations`` are dicts with ``sequence``, ``value`` and ``censored``.
    The winner is the lowest held-out negative log predictive density: a recipe
    that is accurate but overconfident loses to one that knows what it does not
    know, which is the property batch selection actually consumes.
    """
    obs = [o for o in observations if o.get("value") is not None]
    if len(obs) < 5:
        raise ValueError("need at least 5 measured designs to fit, have %d" % len(obs))
    sequences = [o["sequence"] for o in obs]
    y = np.array([float(o["value"]) for o in obs], dtype=np.float64)
    n_censored = int(sum(1 for o in obs if o.get("censored")))

    evaluated, models = {}, {}
    for recipe in recipes:
        if recipe not in _FIT:
            raise ValueError("recipe %r is not in the registry %r" % (recipe, RECIPES))
        evaluated[recipe] = cross_validate(features, sequences, y, recipe, folds=folds)
        models[recipe] = _FIT[recipe](_design_matrix(features, sequences, recipe), y)
        evaluated[recipe]["hyperparameters"] = models[recipe]["hyperparameters"]
        evaluated[recipe]["log_marginal_likelihood"] = models[recipe]["log_marginal_likelihood"]

    winner = min(recipes, key=lambda r: (evaluated[r]["nlpd"], evaluated[r]["rmse"]))
    run = {
        "feature_block": features.block,
        "n_components": features.n_components,
        "n_observations": len(obs),
        "n_censored": n_censored,
        "recipes": evaluated,
        "winner": winner,
        "selection_rule": "lowest held-out nlpd, ties to lower rmse",
        "model": models[winner],
        "models": models,
        "training_sequences": sequences,
        "incumbent": float(y.max()),
    }
    if predict_pool:
        D = features.X if winner == "ridge_onehot" else features.Z
        mu, sd = _PREDICT[winner](models[winner], D)
        run["pool_mean"], run["pool_sd"] = quantize(mu, sd)
    return run


def quantize(*arrays):
    """Round predictions to the precision at which they are stored.

    Three surfaces have to select the same batch from the same snapshot: the
    CLI scripts, the evaluator, and numpy under WebAssembly in the browser.
    They do not agree in the last bits of a float, and they do not have to,
    because the ties here are not corner cases -- every double mutant at a
    pair of positions the model has not seen jointly carries bit-identical
    predictive variance, so the top of an uncertainty ranking is dozens of
    designs deep in exact ties and a difference at the fifteenth decimal
    decides which one is measured.

    The project already hashes canonical JSON at fixed precision for exactly
    this reason. Predictions that drive a selection get the same treatment, so
    the number written into the model run is the number the selection saw.
    """
    out = tuple(np.round(np.asarray(a, dtype=np.float64), schema.FLOAT_PRECISION)
                for a in arrays)
    return out[0] if len(out) == 1 else out


def predict(run, features, sequences, recipe=None):
    recipe = recipe or run["winner"]
    D = _design_matrix(features, sequences, recipe)
    return quantize(*_PREDICT[recipe](run["models"][recipe], D))


def run_summary(run):
    """The JSON-safe part of a model run: everything except the fitted arrays."""
    return {
        "feature_block": run["feature_block"],
        "n_components": run["n_components"],
        "n_observations": run["n_observations"],
        "n_censored": run["n_censored"],
        "winner": run["winner"],
        "selection_rule": run["selection_rule"],
        "incumbent": run["incumbent"],
        "recipes": {k: {kk: vv for kk, vv in v.items()} for k, v in run["recipes"].items()},
    }
