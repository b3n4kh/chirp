#!/bin/bash -x

OUTPUT=$(echo "c:\\cygwin\\${1}/" | sed 's/\//\\/'g)

VERSION=$(cat build/version)
ZIP=${OUTPUT}chirp-$VERSION-win32.zip
IST=${OUTPUT}chirp-$VERSION-installer.exe
LOG=d-rats_build.log

export GTK_BASEPATH='C:\GTK'
export PATH=$PATH:/cygdrive/c/GTK/bin

shift

build_locale() {
	/bin/find.exe . -name '*.py'
	make -C locale
}

build_win32() {
	echo Building Win32 executable...
	/cygdrive/c/Python27/python.exe setup.py py2exe >> $LOG
	if [ $? -ne 0 ]; then
		echo "Build failed"
		exit
	fi
}

copy_lib() {
	echo Copying GTK lib, etc, share...
	cp -r /cygdrive/c/GTK/{lib,etc,share} dist
}

copy_data() {
	mkdir dist
	list="COPYING *.xsd stock_configs locale"
	for i in $list; do
		cp -rv $i dist >> $LOG
	done
}

make_zip() {
	echo Making ZIP archive...
	(cd dist && zip -9 -r $ZIP .) >> $LOG
}

make_installer() {
	echo Making Installer...
	cat > chirp.nsi <<EOF
Name "CHIRP Installer"
OutFile "${IST}"
InstallDir \$PROGRAMFILES\CHIRP
DirText "This will install CHIRP v$VERSION"
#Icon d-rats2.ico
SetCompressor 'lzma'
Section ""
  InitPluginsDir
  RMDir /r "\$INSTDIR"
  SetOutPath "\$INSTDIR"
  File /r 'dist\*.*'
  CreateDirectory "\$SMPROGRAMS\CHIRP"
  CreateShortCut "\$SMPROGRAMS\CHIRP\CHIRP.lnk" "\$INSTDIR\chirpw.exe"
  Delete "\$SMPROGRAMS\CHIRP\CSV Dump.lnk"
  WriteUninstaller \$INSTDIR\Uninstall.exe
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CHIRP" "DisplayName" "CHIRP"  
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CHIRP" "UninstallString" \$\"\$INSTDIR\Uninstall.exe\$\""  
SectionEnd
Section "Uninstall"
  RMDir /r "\$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CHIRP"
  RMDir /r "\$SMPROGRAMS\CHIRP"
SectionEnd
EOF
	unix2dos chirp.nsi
	/cygdrive/c/Program\ Files/NSIS/makensis chirp.nsi
}

rm -f $LOG

build_locale
copy_data
build_win32
copy_lib

if [ "$1" = "-z" ]; then
	make_zip
elif [ "$1" = "-i" ]; then
	make_installer
elif [ -z "$1" ]; then
	make_zip
	make_installer
fi
	
