## Contributing

* I’m not going be working on/maintaining vmdiff for at least 12 months, maybe ever
* I’d _love_ for someone to steal this genius idea, either forking the prototype, or making their own

## Future work

* If a Windows disk has corrupted sectors, `dfvfs` can’t read those sectors. This comes up a lot, and while you can run `chkdsk` on the VM to get around it, it would be nice to not have to.
* It would be nice to be able to diff snapshots of your actual computer, not a virtual machine, but this is hard without external storage
  * The two snapshots of your disk may not fit on your disk itself, to say nothing of the memory snapshots

* See the [blog post](https://community.atlassian.com/t5/Trust-Security-articles/Introducing-vmdiff-a-tool-to-find-everything-that-changes-on/ba-p/2321969) for allll the good details
