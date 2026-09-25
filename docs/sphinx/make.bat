@ECHO OFF
REM Windows counterpart of Makefile — see docs/sphinx/README.md.

pushd %~dp0

if "%SPHINXBUILD%" == "" set SPHINXBUILD=sphinx-build
if "%SPHINXOPTS%" == "" set SPHINXOPTS=-W -n
set SOURCEDIR=.
set BUILDDIR=_build

if "%1" == "" goto help
if "%1" == "html" goto html
if "%1" == "clean" goto clean
if "%1" == "apidoc" goto apidoc

%SPHINXBUILD% -M %1 %SOURCEDIR% %BUILDDIR% %SPHINXOPTS%
goto end

:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR% %SPHINXOPTS%
goto end

:html
%SPHINXBUILD% -b html %SPHINXOPTS% %SOURCEDIR% %BUILDDIR%\html
goto end

:clean
if exist %BUILDDIR% rmdir /s /q %BUILDDIR%
goto end

:apidoc
sphinx-apidoc -f -e -o api ..\..\Glaneur
for %%f in (api\Glaneur.rst api\Glaneur.sources.rst api\Glaneur.updater.rst) do (
    python -c "import sys,re,pathlib;p=pathlib.Path(sys.argv[1]);t=p.read_text(encoding='utf-8');p.write_text(re.sub(r'\nModule contents\n-+\n\n\.\. automodule::[^\n]*\n(?:   :[^\n]*\n)+','\n',t),encoding='utf-8')" %%f
)
goto end

:end
popd
