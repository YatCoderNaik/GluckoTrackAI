#!/bin/bash
set -e

echo "Starting GlucoTrack AI Streamlit Dashboard..."

# 1. Setup Oracle Wallet if it exists in Secrets
if [ -f "/secrets/wallet.zip" ]; then
    echo "Found Oracle Wallet zip in secrets. Unzipping to $LOCAL_WALLET_DIR..."
    unzip -o /secrets/wallet.zip -d "$LOCAL_WALLET_DIR"
    echo "Wallet setup complete."
    ls -l "$LOCAL_WALLET_DIR"
else
    echo "No wallet zip found at /secrets/wallet.zip."
fi

# 2. Check Toolbox and Environment
if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: DB_PASSWORD environment variable is NOT set. Toolbox will fail."
    # We don't exit here to allow the container to start for debugging, 
    # but the app will show errors.
fi

if command -v toolbox &> /dev/null; then
    echo "Toolbox binary found."
else
    echo "Toolbox binary NOT found!"
    exit 1
fi

# 3. Start Streamlit
echo "Launching Streamlit on Port $PORT..."
exec streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
