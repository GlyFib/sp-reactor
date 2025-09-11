"""
Command-line interface for exporting synthesis atomic commands to CSV.
"""

import argparse
import sys
from pathlib import Path
import logging

from .command_exporter import SynthesisCommandExporter


def main():
    parser = argparse.ArgumentParser(
        description="Export atomic device commands from synthesis programs to CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export commands for aa_addition_cycle at 0.1 mmol scale
  python -m src.functions.command_export_cli aa_addition_cycle --scale 0.1
  
  # Export with custom output filename
  python -m src.functions.command_export_cli aa_addition_cycle --scale 0.5 --output my_synthesis_commands.csv
  
  # Export to specific directory
  python -m src.functions.command_export_cli aa_addition_cycle --scale 0.1 --output-dir /path/to/exports
        """
    )
    
    parser.add_argument(
        'program_id',
        nargs='?',
        help='ID of the synthesis program to export (e.g., aa_addition_cycle)'
    )
    
    parser.add_argument(
        '--scale', '-s',
        type=float,
        default=0.1,
        help='Target synthesis scale in mmol (default: 0.1)'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Output CSV filename (auto-generated if not specified)'
    )
    
    parser.add_argument(
        '--output-dir', '-d',
        type=Path,
        default='output/command_exports',
        help='Output directory for CSV files (default: output/command_exports)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--list-programs',
        action='store_true',
        help='List available synthesis programs and exit'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format='%(levelname)s: %(message)s'
    )
    
    try:
        if args.list_programs:
            from ..programs.programs import get_program_registry
            registry = get_program_registry()
            programs = registry.list_programs()
            
            print("Available synthesis programs:")
            for program_id in sorted(programs):
                print(f"  - {program_id}")
            return 0
        
        if not args.program_id:
            parser.error("program_id is required when not using --list-programs")
        
        # Create exporter
        exporter = SynthesisCommandExporter(output_dir=args.output_dir)
        
        # Export commands
        print(f"Exporting atomic commands for synthesis program: {args.program_id}")
        print(f"Scale: {args.scale} mmol")
        
        csv_path = exporter.export_synthesis_commands(
            program_id=args.program_id,
            target_scale_mmol=args.scale,
            output_filename=args.output
        )
        
        print(f"✅ Export successful!")
        print(f"📁 CSV file: {csv_path.absolute()}")
        
        # Show summary
        with open(csv_path, 'r') as f:
            line_count = len(f.readlines())
        
        print(f"📊 Total lines: {line_count}")
        print(f"🔍 Use any spreadsheet application or text editor to view the detailed command sequence")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())