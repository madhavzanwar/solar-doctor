"""SolarDoctor physics + forecasting backend (pvlib expected power, forecasts, anomalies, diagnosis).

Ported from SolarPulseAI (MIT), converted to sync SQLAlchemy 2.0. Importing this package registers
the physics tables on the shared ``Base``.
"""
from solardoctor.physics import models  # noqa: F401  (registers tables on Base)
