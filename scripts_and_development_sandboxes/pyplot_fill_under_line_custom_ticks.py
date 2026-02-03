import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# 1. Setup Data
x = np.linspace(0, 10, 100)
y = np.sin(x) + 2

# Define your custom tick arrays
major_ticks = [0, 2.5, 5, 7.5, 10]
minor_ticks = np.arange(0, 10.1, 0.5)

fig, ax = plt.subplots(figsize=(8, 5))

# 2. Plot the line
ax.plot(x, y, color='dodgerblue', linewidth=2, label='Signal')
# ax.step(x, y, color='dodgerblue', linewidth=2, label='Signal')

# 3. Fill under the line (with transparency)
# 'alpha' controls transparency (0 is invisible, 1 is opaque)
ax.fill_between(x, y, color='dodgerblue', alpha=0.3)

# 4. Set Custom Ticks
# Use FixedLocator for specific arrays
ax.xaxis.set_major_locator(ticker.FixedLocator(major_ticks))
ax.xaxis.set_minor_locator(ticker.FixedLocator(minor_ticks))

# Optional: Style the ticks for better visibility
ax.tick_params(axis='x', which='major', length=10, width=2, color='black')
ax.tick_params(axis='x', which='minor', length=5, width=1, color='gray')

# Add grid and labels
ax.grid(which='major', linestyle='--', alpha=0.6)
plt.title("Customized Line Plot with Fill")
plt.legend()

plt.show()