#!/bin/bash
set -e

echo "Starting GlucoTrack AI Container..."

# 1. Setup Oracle Wallet if it exists in Secrets
if [ -f "/secrets/wallet.zip" ]; then
    echo "Found Oracle Wallet zip in secrets. Unzipping to $LOCAL_WALLET_DIR..."
    unzip -o /secrets/wallet.zip -d "$LOCAL_WALLET_DIR"
    echo "Wallet setup complete."
    ls -l "$LOCAL_WALLET_DIR"
else
    echo "No wallet zip found at /secrets/wallet.zip."
fi

# 2. Check Toolbox
if command -v toolbox &> /dev/null; then
    echo "Toolbox binary found."
else
    echo "Toolbox binary NOT found!"
    exit 1
fi

# 3. Start the Bot
export MODE=webhook
echo "Starting Bot on Port $PORT..."
exec python bot.py
