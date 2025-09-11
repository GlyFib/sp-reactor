# Virtual Peptide Synthesizer (VPR) - User Guide

A comprehensive automated peptide synthesis system with hardware integration, simulation capabilities, and advanced command export functionality.

## Quick Start

### Basic Usage Examples

```bash
# Interactive mode (recommended for first-time users)
python main.py

# Generate recipe only (no execution)
python main.py --recipe-only --sequence data/sequences/f.txt --scale 0.1

# Simulated synthesis execution
python main.py --simulated --sequence data/sequences/fmrfamide.txt --scale 0.1

# Real hardware execution (requires Arduino Opta connection)
python main.py --sequence data/sequences/fmrfamide.txt --serial-port COM3 --scale 0.1

# Use custom configuration
python main.py --config data/config/standard.yaml --sequence data/sequences/rkdv.txt
```

## System Overview

The VPR system operates on a three-layer architecture:

1. **Hardware Layer** - Direct device control (Arduino Opta, VICI valve, Masterflex pump, solenoid)
2. **Function Layer** - Atomic and composite synthesis operations
3. **Coordination Layer** - High-level synthesis scheduling and execution

## Operation Modes

### 1. Recipe Generation Mode (`--recipe-only`)

Generates detailed synthesis protocols without executing them.

```bash
# Generate CSV recipe for a simple peptide
python main.py --recipe-only --sequence data/sequences/f.txt --scale 0.1

# Generate JSON format recipe
python main.py --recipe-only --sequence data/sequences/fmrfamide.txt --output-format json

# Custom output directory
python main.py --recipe-only --sequence data/sequences/rkdv.txt --output-dir my_recipes
```

**Outputs:**
- Recipe files (CSV/JSON/YAML format)
- Atomic command sequences with timing
- Reagent consumption reports
- Volume calculations

### 2. Simulation Mode (`--simulated`)

Full synthesis simulation without hardware requirements.

```bash
# Basic simulation
python main.py --simulated --sequence data/sequences/fmrfamide.txt --scale 0.1

# Fast simulation (10x speed)
python main.py --simulated --sequence data/sequences/rkdv.txt --fast

# Custom speed control
python main.py --simulated --sequence data/sequences/f.txt --speed 0.5
```

**Features:**
- Real-time progress monitoring
- Command execution tracking
- Hardware state simulation
- Error condition testing

### 3. Hardware Execution Mode (Default)

Real synthesis execution on connected hardware.

```bash
# Basic hardware execution
python main.py --sequence data/sequences/f.txt --serial-port COM3

# With custom hardware parameters
python main.py --sequence data/sequences/fmrfamide.txt \
    --serial-port /dev/ttyUSB0 \
    --ml-per-rev 0.8 \
    --vici-id VICI_01
```

**Requirements:**
- Arduino Opta connected via USB
- VICI selector valve (16-position)
- Masterflex peristaltic pump
- Solenoid valve for vacuum control

### 4. Interactive Mode

Step-through interface for learning and debugging.

```bash
# Launch interactive mode
python main.py

# Interactive with custom config
python main.py --config data/config/hardware.yaml
```

## Configuration Files

### Hardware Configuration (`data/config/hardware.yaml`)

Controls hardware-specific settings:

```yaml
opta:
  serial_port: "COM3"              # Adjust for your system
  baud_rate: 115200
  connection_timeout_seconds: 5

devices:
  vici_valve:
    device_id: "VICI_01"
    positions: 16
  
  masterflex_pump:
    device_id: "MFLEX_01" 
    ml_per_revolution: 0.8          # Calibration value
  
  solenoid_valve:
    relay_id: "REL_04"
```

### Synthesis Configuration (`data/synthesis/*.yaml`)

Defines synthesis parameters:

```yaml
# Basic synthesis setup
sequence: "FMRF"
scale:
  target_mmol: 0.1
  loading_mmol_g: 0.5

# Chemistry programs
default_aa_program: "aa_oxyma_dic_v1"
perform_capping: true
double_couple_difficult: false
```

### Standard Configuration (`data/config/standard.yaml`)

General system settings:

```yaml
display:
  progress_bar_width: 40
  show_details_default: false

hardware:
  flow_rate_ml_min: 2.0
  simulation_mode: true
  wash_volume_per_gram: 6.0

output:
  include_timestamps: true
```

## Sequence Files

### Simple Text Format (`data/sequences/*.txt`)

Single line with amino acid sequence:
```
FMRF
```

### Advanced CSV Format

Coming soon - will support position-specific parameters.

## Available Sequences

The system includes example sequences:

- `data/sequences/f.txt` - Single phenylalanine (testing)
- `data/sequences/fmrfamide.txt` - FMRFamide tetrapeptide
- `data/sequences/rkdv.txt` - RKDV tetrapeptide

## Command Line Options

### Core Options

- `--sequence FILE` - Peptide sequence file (.txt or .csv)
- `--config FILE` - Configuration file (.yaml)
- `--scale MMOL` - Synthesis scale in mmol (default: 0.1)
- `--output-dir DIR` - Output directory (default: output)

### Execution Modes

- `--simulated` - Run in simulation mode
- `--recipe-only` - Generate recipe file only, no execution
- `--fast` - Fast simulation mode (10x speed)
- `--speed MULTIPLIER` - Custom speed multiplier (0.1-10.0)

### Hardware Options

- `--serial-port PORT` - Arduino Opta serial port (e.g., COM3, /dev/ttyUSB0)
- `--ml-per-rev VALUE` - Pump calibration (default: 0.8)
- `--vici-id ID` - VICI valve device ID (default: VICI_01)
- `--pump-id ID` - Pump device ID (default: MFLEX_01)
- `--solenoid-relay-id ID` - Solenoid relay ID (default: REL_04)

### Output Options

- `--output-format {csv,json,yaml}` - Recipe output format (default: csv)
- `--verbose` - Detailed logging output
- `--quiet` - Minimal output

## Output Files

### Generated Files Structure

```
output/
├── recipes/
│   ├── [sequence]_[timestamp]_recipe.csv    # Human-readable protocol
│   ├── [sequence]_[timestamp].json          # Machine-readable data
│   └── [sequence]_[timestamp]_commands.csv  # Atomic command sequence
├── logs/
│   └── synthesis_[timestamp].log            # Execution logs
└── reports/
    └── reagent_consumption_[timestamp].csv  # Volume tracking
```

### Recipe File Contents

**CSV Recipe Format:**
- Step-by-step synthesis protocol
- Reagent volumes and timing
- Washing procedures
- Coupling/deprotection cycles

**Commands CSV Format:**
- Low-level device commands
- Precise timing information
- Hardware state transitions
- Error handling instructions

## Troubleshooting

### Common Issues

1. **Serial Port Connection**
   ```bash
   # List available ports (Windows)
   python -m serial.tools.list_ports
   
   # Test connection
   python main.py --simulated --sequence data/sequences/f.txt
   ```

2. **Configuration Errors**
   ```bash
   # Create default config
   python main.py --create-config my_config.yaml
   
   # Validate config
   python main.py --config my_config.yaml --recipe-only --sequence data/sequences/f.txt
   ```

3. **Hardware Calibration**
   - Adjust `ml_per_rev` parameter for pump calibration
   - Verify VICI valve position mapping
   - Check solenoid relay assignments

### Debug Mode

```bash
# Verbose logging
python main.py --verbose --sequence data/sequences/f.txt

# Simulation with detailed output
python main.py --simulated --verbose --sequence data/sequences/fmrfamide.txt
```

## Hardware Setup

### Required Components

1. **Arduino Opta** - Main controller with USB connection
2. **VICI 16-Position Selector Valve** - Reagent selection
3. **Masterflex Peristaltic Pump** - Precise fluid dispensing
4. **Solenoid Valve** - Vacuum/drainage control

### Connection Verification

```bash
# Test hardware connectivity
python test_hardware_control.py

# Run atomic commands directly
python run_atomic_commands.py
```

## Advanced Usage

### Custom Chemistry Programs

The system supports custom synthesis protocols via CSV program definitions in `data/programs/`.

### Batch Processing

```bash
# Process multiple sequences
for seq in data/sequences/*.txt; do
    python main.py --recipe-only --sequence "$seq" --scale 0.1
done
```

### Integration with External Systems

Export atomic command sequences for integration with other automation platforms:

```bash
python main.py --recipe-only --sequence data/sequences/fmrfamide.txt --output-format json
```

## Support and Development

- Project documentation: See `CLAUDE.md` for architecture details
- Hardware integration: Phase 2 complete with full device control
- Current phase: Advanced hardware control and optimization

For questions or issues, refer to the project documentation or examine the simulation mode output for debugging synthesis protocols.