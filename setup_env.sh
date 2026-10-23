#!/bin/bash
set -e

# Compile minimal libGL stub if libGL.so.1 does not exist
if [ ! -f /usr/lib/x86_64-linux-gnu/libGL.so.1 ]; then
    echo "Configuring libGL stub for headless/container Qt support..."
    cat << 'EOF' > /tmp/dummy_gl.c
void glLoadIdentity(void) {}
void glLoadMatrixf(const float *m) {}
void glMatrixMode(unsigned int mode) {}
void glOrtho(double left, double right, double bottom, double top, double nearVal, double farVal) {}
EOF
    gcc -shared -fPIC -o /tmp/libGL.so.1 /tmp/dummy_gl.c
    sudo cp /tmp/libGL.so.1 /usr/lib/x86_64-linux-gnu/libGL.so.1
    sudo /sbin/ldconfig 2>/dev/null || true
fi

# Install dependencies if missing
python3 -c "import PyQt5, requests, pytest" 2>/dev/null || {
    echo "Installing requirements..."
    python3 -m pip install --break-system-packages -r requirements.txt
}

echo "Environment is ready!"
