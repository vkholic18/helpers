val secondResourceIds = catalog_relationship.select(col("second_resource_id")).distinct()

// Step 2: Perform a LEFT ANTI join to filter out matching rows (finding top-level parents)
val getTopLevelParent = catalog_relationship
  .select(
    col("first_resource_id").alias("destination"),
    lit(null).cast("string").alias("source"),  // Initially, source is null
    col("first_resource_id").alias("root")     // Root is initialized to itself
  )
  .join(secondResourceIds, col("destination") === col("second_resource_id"), "left")
  .filter(col("second_resource_id").isNull)   // Equivalent to LEFT ANTI join
  .drop("second_resource_id")                 // Drop unwanted column

// Step 3: Recursively build the hierarchy
var resultDf = getTopLevelParent

// Recursive loop with renamed variable "TopLevelEs"
var TopLevelEs = getTopLevelParent
do {
  resultDf = TopLevelEs

  TopLevelEs = catalog_relationship
    .join(resultDf, catalog_relationship("second_resource_id") === resultDf("destination"), "inner")
    .select(
      col("first_resource_id").alias("destination"),
      col("second_resource_id").alias("source"),
      resultDf("root")
    )
    .union(resultDf)  // Add new parent-child mappings and retain previous mappings
    .distinct()       // Remove duplicates

} while (TopLevelEs.count() > resultDf.count())
