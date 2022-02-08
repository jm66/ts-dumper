## Transkribus dumper

### Installation

1. Clone from repo or download the source code.
2. Create a `python 3` virtual environment:
   ```shell script
   python3 -m venv venv && source venv/bin/activate
   ```
 
3. Execute the `ts-dumper.py` script to install the requirements.
4. At this point all requirements must be installed.

### Use

   ```shell script
       ./ts-dumper.py --help   
      Usage: ts-dumper.py [OPTIONS]
      
        Run main cli.
      
      Options:
        -v, --verbosity LVL     Either CRITICAL, ERROR, WARNING, INFO or DEBUG
        --version               Show the version and exit.
        --collection-name TEXT  Collection name  [required]
        --username TEXT         Transkribus username.  [required]
        --password TEXT         Transkribus username password.
        --target-dir PATH       Target directory where files will be written.
        -x                      Print back traces when exception occurs.  [env var:
                                VSS_EM_EXC]
        --help                  Show this message and exit.
   
   ```

### Troubleshooting

Options like `--loglevel=DEBUG` and `-x` in the command, can provide details to 
where the script might be failing.