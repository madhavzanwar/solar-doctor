"""SolarDoctor forecasting package (ported from SolarPulseAI, MIT).

Feature pipeline (pvlib), LightGBM hybrid + probabilistic forecasters, online residual adapter,
post-processing (clipping, soiling, ramp risk) and training code.
"""
from ml.forecast.config import PlantConfig

__all__ = ["PlantConfig"]
