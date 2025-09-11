# VPR Phase 2: Synthesis and Program Layer Analysis

## Overview

The VPR system implements a four-layer architecture for automated peptide synthesis. This document provides a detailed analysis of **Layer 3 (Program Management)** and **Layer 4 (Synthesis Coordination)**, including their inputs, outputs, interactions, and deprecated components.

## Layer 4: Synthesis Coordination (`src/synthesis/`)

### Architecture Overview

The synthesis layer coordinates high-level synthesis operations, converting peptide sequences into executable synthesis schedules.

### Key Components

#### 1. SynthesisCoordinator (`coordinator.py`)
**Purpose**: Main orchestrator for peptide synthesis planning and execution.

**Input Processing**:
- **Peptide Sequence**: Text string (e.g., "FMRF") or sequence files
- **Target Scale**: mmol scale (e.g., 0.1 mmol)
- **Synthesis Parameters**: From `SynthesisParameters` dataclass
- **Program Selection**: AA program names, begin/end programs
- **Configuration Files**: YAML synthesis configs from `data/synthesis/`

**Core Workflow**:
1. **Sequence Parsing**: Converts sequence strings to `PeptideSequence` objects
2. **Schedule Creation**: Builds step-by-step `SynthesisSchedule` with timing and reagents
3. **Program Integration**: Links synthesis steps to executable programs
4. **Parameter Substitution**: Converts template parameters (v_1, v_2) to actual volumes
5. **Export Generation**: Outputs schedules as JSON, CSV, or YAML

**Key Methods**:
- `create_synthesis_schedule()`: Main scheduling function
- `generate_executable_program()`: Converts synthesis steps to executable programs
- `_create_aa_addition_step()`: Creates amino acid coupling steps
- `substitute_program_parameters()`: Template parameter substitution

**Output Generation**:
- **SynthesisSchedule**: Complete synthesis plan with steps, timing, reagents
- **Executable Programs**: JSON programs with calculated volumes
- **Export Files**: CSV atomic commands, JSON recipes, YAML schedules

#### 2. StoichiometryCalculator (`stoichiometry.py`)
**Purpose**: Chemistry calculations for reagent volumes and masses.

**Input Sources**:
- **Stoichiometry Config**: YAML files with excess ratios, standard volumes
- **Reagent Database**: Built-in reagents (Fmoc-AAs, coupling agents, solvents)
- **Chemistry Parameters**: Excess ratios, volumes per gram/mmol

**Calculation Methods**:
- `calculate_coupling_volumes()`: AA and activator volumes
- `calculate_wash_volumes()`: Solvent wash volumes
- `calculate_deprotection_volume()`: Piperidine/DMF volumes
- `get_coupling_time()`: Chemistry-specific reaction times

**Legacy vs Current**:
- **Legacy**: `calculate_coupling_volumes_legacy()` - detailed stoichiometry with individual reagents
- **Current**: Simplified volumes based on `coupling_volume_per_mmol` from enhanced CSV programs

#### 3. ParameterSubstitution (within `coordinator.py`)
**Purpose**: Template parameter replacement in programs.

**Template Patterns**:
- `{{ v_1 }}`: Deprotection volume placeholder
- `{{ v_2 }}`: Coupling solution volume placeholder  
- `{{ v_3 }}`: Wash volume placeholder
- `{{ coupling_time }}`: Reaction time placeholder

**Substitution Process**:
1. Load program JSON with templates
2. Calculate actual values using stoichiometry
3. Replace placeholders with calculated values
4. Return executable program structure

### Input Files and Configurations

#### Required Inputs
1. **Peptide Sequence**: 
   - Text files (`.txt`) with single-letter AA codes
   - Direct string input via CLI arguments
   - Example: `"FMRF"` for Phe-Met-Arg-Phe peptide

2. **Scale Parameter**:
   - Target scale in mmol (typically 0.1-1.0 mmol)
   - Affects all volume calculations

3. **Synthesis Configuration** (`data/synthesis/*.yaml`):
   ```yaml
   sequence: "FMRF"
   scale:
     target_mmol: 0.1
     loading_mmol_g: 0.5
   default_aa_program: "aa_oxyma_dic_v1"
   double_couple_difficult: false
   perform_capping: true
   ```

#### Optional Configuration Files
- **Hardware Config** (`data/config/hardware.yaml`): Device-specific settings
- **Standard Config** (`data/config/standard.yaml`): Default synthesis parameters
- **Custom Stoichiometry**: Program-specific chemistry parameters

### Output Products

#### 1. Synthesis Schedule (JSON)
```json
{
  "synthesis_id": "SYNTH_FMRF_20240907_194640",
  "peptide_sequence": "FMRF",
  "target_scale_mmol": 0.1,
  "steps": [
    {
      "step_number": 1,
      "amino_acid": "F",
      "program_name": "aa_oxyma_dic_v1",
      "parameters": {"resin_mmol": 0.1},
      "estimated_time_minutes": 180.0,
      "reagents_consumed": {"Fmoc-F": 1.6, "DMF": 6.4}
    }
  ],
  "total_estimated_time_minutes": 720.0
}
```

#### 2. Atomic Command Tables (CSV)
Generated for hardware execution tracking:
```csv
seq,function_id,device,volume_ml,time_seconds,comments
1,valve_set_position,VICI,0,0,Set valve to R3 (deprotection)
2,pump_dispense,Masterflex,1.6,0,Dispense 1.6 mL piperidine/DMF
3,vacuum_on,Solenoid,0,60,Drain for 60 seconds
```

## Layer 3: Program Management (`src/programs/`)

### Architecture Overview

The program layer manages synthesis protocols as reusable, parameterized programs with integrated chemistry.

### Key Components

#### 1. Enhanced CSV Programs
**Format**: CSV files with integrated chemistry calculations

**Structure** (`data/programs/aa_oxyma_dic_v1.csv`):
```csv
step_id,group_id,loop_type,loop_times,function_id,volume_per_mmol,time_seconds,reagent_port,dest_port,comments
1,1,All,,Meter_R3_MV,16.0,,R3,MV,Fmoc deprotection (16 mL/mmol piperidine)
2,1,All,,Transfer_MV_RV_Time,,60,MV,RV,Transfer to reactor for 60 sec
5,2,NL,4,Meter_R4_MV,16.0,,R4,MV,DMF wash (16 mL/mmol x4 cycles)
```

**Key Features**:
- **Integrated Chemistry**: `volume_per_mmol` column contains stoichiometry
- **Scale Independence**: Programs work at any synthesis scale
- **Loop Support**: `NL` (nested loop) for repeated operations
- **Port Mapping**: Direct hardware port assignments (`R1`, `R2`, etc.)

#### 2. CSV Compiler (`csv_compiler.py`)
**Purpose**: Compiles CSV programs into executable JSON with calculated volumes.

**Compilation Process**:
1. **CSV Parsing**: Read enhanced CSV format
2. **Loop Expansion**: Expand `NL` blocks into individual steps
3. **Volume Calculation**: Apply scale-specific chemistry (`volume_per_mmol * target_scale`)
4. **Executable Generation**: Output JSON with calculated parameters

**Input**: `aa_oxyma_dic_v1.csv` + target scale (0.1 mmol)
**Output**: `aa_oxyma_dic_v1_0p1mmol_31109abd.json` with calculated volumes

#### 3. Program Registry (`programs.py`)
**Purpose**: Discovery and management of available programs.

**Program Discovery**:
- Scans `data/programs/` directory for CSV programs
- Builds registry of available programs
- Handles program versioning and compilation

**Program Types**:
- **Enhanced CSV**: New format with integrated chemistry
- **Legacy JSON**: Old format with external stoichiometry (deprecated)

### Program vs Legacy Systems

#### Current Enhanced System
- **Programs contain chemistry**: Volume calculations in CSV
- **Scale-independent**: Programs work at any synthesis scale  
- **Simplified coordination**: Synthesis layer just applies scale factor
- **Hardware integration**: Direct port assignments in CSV

#### Legacy System (Deprecated Components)
- **External stoichiometry**: Separate YAML files for chemistry
- **Complex parameter substitution**: Template-based volume calculation
- **Program-agnostic chemistry**: Same stoichiometry for all programs

**Deprecated Functions Identified**:
- `calculate_coupling_volumes_legacy()` in stoichiometry.py:181
- `_create_legacy_aa_addition_step()` in coordinator.py:415
- `_load_program_stoichiometry()` in coordinator.py:559 (marked DEPRECATED)
- Legacy JSON program loader in CLI display.py:419

## Integration Flow

### Complete Synthesis Process
1. **Input Processing** (Layer 4):
   - User provides sequence + scale
   - System loads synthesis config
   - Coordinator parses peptide sequence

2. **Program Selection** (Layer 3):
   - Enhanced program registry consulted
   - CSV program loaded for each synthesis step
   - Programs compiled for target scale

3. **Schedule Generation** (Layer 4):
   - Synthesis steps created for each amino acid
   - Program parameters calculated
   - Complete schedule with timing/reagents

4. **Execution Preparation** (Layers 2 & 1):
   - Executable programs passed to functions layer
   - Functions layer converts to hardware commands
   - Hardware adapter executes on actual devices

### Data Flow Summary

```
Peptide Sequence ("FMRF") + Scale (0.1 mmol)
    ↓
Synthesis Coordinator (Layer 4)
    ↓
Enhanced CSV Program (Layer 3: aa_oxyma_dic_v1.csv)
    ↓
CSV Compiler: volume_per_mmol * target_scale 
    ↓
Executable Program (calculated volumes)
    ↓
Functions Layer (Layer 2) → Hardware Commands
    ↓
Hardware Adapter (Layer 1) → Physical Devices
```

## Current State Assessment

### Fully Operational ✅
- Enhanced CSV programs with integrated chemistry
- Scale-independent synthesis planning
- Atomic command export for hardware execution
- Multi-format export (JSON, CSV, YAML)

### Deprecated but Maintained 🟡
- Legacy stoichiometry calculations (backward compatibility)
- Template parameter substitution (for old programs)
- External stoichiometry YAML files

### TODO Items 📋
- Make mock mode configurable in programs.py:89
- Consider removing deprecated legacy functions after full enhanced CSV migration
- Enhanced error handling for missing or invalid programs

## Recommendations

1. **Complete Enhanced CSV Migration**: Remove remaining legacy stoichiometry dependencies
2. **Program Validation**: Add validation for CSV program completeness and chemistry consistency  
3. **Advanced Chemistry**: Support temperature control and alternative coupling strategies in CSV format
4. **Performance Optimization**: Cache compiled programs for repeated synthesis runs

This architecture provides a robust, chemistry-aware synthesis planning system that successfully bridges high-level peptide sequences to low-level hardware control.