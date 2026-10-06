"""Legacy file kept for upgrade compatibility.

Meta Pixel no longer hooks into payment.transaction._post_process().  Purchase
CAPI delivery is handled by an independent cron in meta.pixel.config so Meta
tracking can never block, cancel, delay, or roll back the checkout lifecycle.
"""
