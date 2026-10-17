// Prototype the upper case with four cylindrical cutouts and an added top plate.
// Dimensions are in millimetres; the imported mesh supplies the base geometry.
$fn=180;

// Common cutout diameter; keep all four openings identical.
d=13.5;




difference() {

    union() {
        import("CaseUpper.3mf");
        translate([0,0,28.8])cube([45,80,2],true);
    }


    translate([-16,0,-1]) cylinder(d=d,100);
    translate([16,0,-1]) cylinder(d=d,100);
    translate([0,30,-1]) cylinder(d=d,100);
    translate([0,-30,-1]) cylinder(d=d,100);


}
