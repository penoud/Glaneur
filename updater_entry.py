from WpImageDownloader.updater.windows import run_updater

if __name__ == "__main__":
    import sys
    raise SystemExit(run_updater(sys.argv[1:]))
