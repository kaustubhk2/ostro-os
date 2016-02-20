#!/bin/sh
# Hook to add source component/revision info to commit message
# Parameter:
#   $1 patch-file
#   $2 revision
#   $3 reponame

patchfile=$1
rev=$2

# Don't mangle subject and use shorter OE-core instead of openembedded-core.
reponame=OE-core

if grep -q '^Signed-off-by:' $patchfile; then
    # Insert before Signed-off-by.
    sed -i -e "0,/^Signed-off-by:/s#\(^Signed-off-by:.*\)#\(From $reponame rev: $rev\)\n\n\1#" $patchfile
else
    # Insert before final --- separator, with extra blank lines removed.
    perl -e "\$_ = join('', <>); s/^(.*\S[ \t]*)(\n|\n\s*\n)---\n/\$1\n\nFrom $reponame rev: $rev\n---\n/s; print;" $patchfile >$patchfile.tmp
    mv $patchfile.tmp $patchfile
fi
