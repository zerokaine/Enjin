// Node constraints and indexes for Enjin entity graph

// Unique constraints
CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT organization_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT location_id IF NOT EXISTS FOR (l:Location) REQUIRE l.id IS UNIQUE;
CREATE CONSTRAINT asset_id IF NOT EXISTS FOR (a:Asset) REQUIRE a.id IS UNIQUE;

// Fulltext indexes for search
CREATE FULLTEXT INDEX person_name IF NOT EXISTS FOR (p:Person) ON EACH [p.name, p.aliases];
CREATE FULLTEXT INDEX org_name IF NOT EXISTS FOR (o:Organization) ON EACH [o.name, o.aliases];
CREATE FULLTEXT INDEX event_title IF NOT EXISTS FOR (e:Event) ON EACH [e.title, e.summary];
CREATE FULLTEXT INDEX location_name IF NOT EXISTS FOR (l:Location) ON EACH [l.name, l.country];

// Property indexes for filtering
CREATE INDEX person_type IF NOT EXISTS FOR (p:Person) ON (p.type);
CREATE INDEX org_type IF NOT EXISTS FOR (o:Organization) ON (o.type);
CREATE INDEX event_category IF NOT EXISTS FOR (e:Event) ON (e.category);
CREATE INDEX event_date IF NOT EXISTS FOR (e:Event) ON (e.occurred_at);
CREATE INDEX location_country IF NOT EXISTS FOR (l:Location) ON (l.country);
CREATE INDEX location_coords IF NOT EXISTS FOR (l:Location) ON (l.latitude, l.longitude);
