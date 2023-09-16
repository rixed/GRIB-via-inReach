Comment utiliser l'image docker:

 % docker run -ti --network=host -e DISPLAY=:0 rixed/grib-via-inreach-clt

Note: Pour Windows, il est *probable* que la ligne de commande correcte soit plutôt:

 % docker run -ti -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg -e DISPLAY=:0 rixed/grib-via-inreach-clt

Et on se retrouve normalement dans un shell.

Là, on *doit* pouvoir lancer XyGrib:

 % XyGrib

(et il devrait s'afficher)


Mais surtout, on peut lancer:

1. nano

C'est un éditeur de texte tout simple, dans lequel tu peux copier coller les messages reçus pour rassembler tous les fragments dans un fichier.
Par exemple:

 % nano

 ... puis copier-coller les fragments, de préférence dans l'ordre ...
 ... puis tapper ^X (Control + X) et dire qu'on veut sauver et donner un nom de fichier ...

2. decode.py

 C'est le décodeur qui va reconstituer le fichier grib à partir du fichier précédent.
 Il faut lancer comme ceci :

 % python3 decode.py -o meteo.grib le_fichier

Et si tout se passe comme prévu, il y aura ensuite un fichier 'meteo.grib', que l'on peut afficher directement avec XyGrib:

 % XyGrib meteo.grib

ou à recopier ailleurs pour le visualiser avec un autre outils.

