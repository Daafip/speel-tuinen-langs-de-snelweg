/* Rest stops + nearby playgrounds for Germany.
 *
 * Pre-filtering playgrounds to those within 300 m of a rest area (around.rest:300)
 * keeps the response light instead of pulling every playground in the country.
 * `.rest out geom` / `.play out geom` emit full geometry so areas survive.
 */
[out:json][timeout:300];
area["ISO3166-1"="DE"][admin_level=2]->.de;
(
  nwr["highway"="services"](area.de);
  nwr["highway"="rest_area"](area.de);
)->.rest;
(
  nwr["leisure"="playground"](around.rest:300);
)->.play;
.rest out geom;
.play out geom;
