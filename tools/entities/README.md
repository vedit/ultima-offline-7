# Trinsic entity import

The private ModernUO profile loads `U7EntitiesHost.dll` with the compiler’s `Campaign/actor.json` and `Campaign/container.json`. It checks the source fingerprint, NPC binding and private map before the first import. The normal shard retains its own configuration and save directories.

Finnigan is a `CampaignActor` at the source position. The ship parts use the barge’s superchunk and each member’s original coordinate bytes. The hold and crate are ModernUO containers. Inventory coordinates remain gump coordinates. The item graphics are presentation substitutions, and ship movement and scheduling are outside this import.

Each imported item or mobile serializes its immutable source ID alongside its ordinary ModernUO data. `CampaignEntities.Find(id)` resolves the live instance. The seed registry prevents re-importing a deleted source object. `SpawnOnce(eventKey, art, location)` stores a separate runtime ID and reuses the same live instance when an event is retried. Handlers call those APIs on the shard game thread.

In-range double-click on Finnigan calls `CampaignEntities.ActorUsed` when a campaign script handler has registered. The binding includes the source function ID. The entity import supplies no authored dialogue or quest choices.

## Verify a disposable server

Run these commands from the repository against the provisioned installation and the staged development facet.

```powershell
.\tools\entities\build.ps1 -Root E:\UltimaOffline -WithReplay
py -3.13 tools\entities\smoke.py --installation E:\UltimaOffline --facet E:\UltimaOffline\Builds\TrinsicFacet --report E:\UltimaOffline\Evidence\trinsic-entity-replay.json
```

The test copies the staged server, selects an unused loopback port and isolates the save path under E: cache. Its separate replay assembly runs only in that copy. The first boot checks record order, moves one duplicate, deletes another, and retries a runtime spawn. The second boot checks both containers, item and mobile serials, coordinates, deletion, and runtime creation against the first observation. It does not require a player account.
